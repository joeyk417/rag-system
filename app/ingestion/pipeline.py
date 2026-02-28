from __future__ import annotations

import asyncio
import logging
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings
from app.core.providers.openai_provider import OpenAIProvider
from app.db.models import Chunk, Document, IngestJob
from app.db.session import tenant_session
from app.ingestion.chunker import chunk_pages
from app.ingestion.embedder import embed_chunks
from app.ingestion.hash_check import compute_hash, find_existing
from app.ingestion.metadata_parser import parse
from app.ingestion.pdf_extractor import extract_pages

logger = logging.getLogger(__name__)


def _s3_upload(pdf_bytes: bytes, s3_key: str) -> None:
    """Synchronous S3 upload — run in a thread via asyncio.to_thread()."""
    client = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )
    client.put_object(
        Bucket=settings.s3_bucket_name,
        Key=s3_key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )


async def run_pipeline(
    job_id: uuid.UUID,
    pdf_bytes: bytes,
    filename: str,
    schema_name: str,
    tenant_config: dict,
    s3_prefix: str,
) -> None:
    """Background-safe ingest pipeline — creates its own DB session."""
    TenantSession = tenant_session(schema_name)

    async with TenantSession() as ts:
        async def _update_job(status: str, **kwargs: object) -> None:
            job = await ts.get(IngestJob, job_id)
            if job is None:
                return
            job.status = status
            for k, v in kwargs.items():
                setattr(job, k, v)
            await ts.commit()

        try:
            await _update_job("processing")

            # 1. Hash + dedup check (second guard — endpoint already checked)
            file_hash = compute_hash(pdf_bytes)
            existing_id = await find_existing(file_hash, ts)
            if existing_id is not None:
                await _update_job("completed", document_id=existing_id)
                logger.info("Skipped duplicate document %s (job %s)", file_hash[:12], job_id)
                return

            # 2. S3 upload (skipped in development)
            s3_key = f"{s3_prefix}{file_hash}/{filename}"
            if settings.app_env != "development":
                try:
                    await asyncio.to_thread(_s3_upload, pdf_bytes, s3_key)
                except (BotoCoreError, ClientError) as exc:
                    raise RuntimeError(f"S3 upload failed: {exc}") from exc
            else:
                logger.info("Development mode — skipping S3 upload, s3_key=%s", s3_key)

            # 3. Extract pages with Docling
            pages = await extract_pages(pdf_bytes)

            # 4. Parse metadata from filename + page 1
            page1_text = pages[0].markdown_text if pages else ""
            meta = parse(filename, page1_text, tenant_config)

            # 5. Chunk pages
            chunks = chunk_pages(pages)

            # 6. Generate embeddings
            provider = OpenAIProvider()
            vectors = await embed_chunks(chunks, provider)

            # 7. Insert Document + Chunks in one transaction
            doc = Document(
                file_hash=file_hash,
                filename=filename,
                s3_key=s3_key,
                doc_number=meta.doc_number,
                doc_type=meta.doc_type,
                revision=meta.revision,
                title=meta.title,
                classification=meta.classification,
                extra_metadata=meta.extra_metadata,
                page_count=len(pages),
                status="completed",
            )
            ts.add(doc)
            await ts.flush()  # get doc.id before commit

            chunk_rows = [
                Chunk(
                    document_id=doc.id,
                    page_number=c.page_number,
                    chunk_index=c.chunk_index,
                    heading=c.heading,
                    content=c.content,
                    embedding=vectors[i],
                    token_count=c.token_count,
                )
                for i, c in enumerate(chunks)
            ]
            ts.add_all(chunk_rows)

            # 8. Update job → completed
            job = await ts.get(IngestJob, job_id)
            if job:
                job.status = "completed"
                job.document_id = doc.id

            await ts.commit()
            logger.info(
                "Ingest completed: doc_id=%s chunks=%d job=%s",
                doc.id,
                len(chunk_rows),
                job_id,
            )

        except Exception as exc:
            await ts.rollback()
            logger.exception("Ingest failed for job %s", job_id)
            # Re-open session to record failure
            async with TenantSession() as err_ts:
                job = await err_ts.get(IngestJob, job_id)
                if job:
                    job.status = "failed"
                    job.error = str(exc)
                    await err_ts.commit()
