from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IngestJob, Tenant
from app.db.session import tenant_session
from app.dependencies import get_db, get_tenant
from app.ingestion.hash_check import compute_hash, find_existing
from app.ingestion.pipeline import run_pipeline
from app.schemas.ingest import IngestResponse, JobStatusResponse

router = APIRouter()


@router.post("", response_model=IngestResponse, status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_tenant),
    session: AsyncSession = Depends(get_db),  # noqa: ARG001 (kept for DI lifecycle)
) -> IngestResponse:
    """Upload a PDF for ingestion. Returns immediately with a job_id to poll."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    TenantSession = tenant_session(tenant.schema_name)

    async with TenantSession() as ts:
        # Fast dedup check BEFORE creating a job
        file_hash = compute_hash(pdf_bytes)
        existing_id = await find_existing(file_hash, ts)
        if existing_id is not None:
            return IngestResponse(
                job_id=None,
                status="completed",
                document_id=existing_id,
                message="Document already ingested",
            )

        # Create IngestJob in the tenant schema
        job = IngestJob(status="pending")
        ts.add(job)
        await ts.commit()
        await ts.refresh(job)
        job_id = job.id

    background_tasks.add_task(
        run_pipeline,
        job_id=job_id,
        pdf_bytes=pdf_bytes,
        filename=file.filename,
        schema_name=tenant.schema_name,
        tenant_config=tenant.config,
        s3_prefix=tenant.s3_prefix,
    )

    return IngestResponse(
        job_id=job_id,
        status="pending",
        message="Ingest started",
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    tenant: Tenant = Depends(get_tenant),
    session: AsyncSession = Depends(get_db),  # noqa: ARG001
) -> JobStatusResponse:
    """Poll the status of an ingest job."""
    TenantSession = tenant_session(tenant.schema_name)
    async with TenantSession() as ts:
        job = await ts.get(IngestJob, job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,  # type: ignore[arg-type]
        document_id=job.document_id,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
