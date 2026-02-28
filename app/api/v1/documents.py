from __future__ import annotations

import logging
from uuid import UUID

import boto3
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.config import settings
from app.db.models import Document, Tenant
from app.db.session import tenant_session
from app.dependencies import get_tenant
from app.schemas.document import DocumentResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    doc_type: str | None = Query(default=None, description="Filter by document type (e.g. SOP, ENG-DRW)"),
    tenant: Tenant = Depends(get_tenant),
) -> list[DocumentResponse]:
    """List documents for the authenticated tenant, ordered by created_at DESC."""
    session_maker = tenant_session(tenant.schema_name)
    async with session_maker() as session:
        stmt = select(Document).order_by(Document.created_at.desc())
        if doc_type is not None:
            stmt = stmt.where(Document.doc_type == doc_type)
        result = await session.execute(stmt)
        docs = result.scalars().all()

    return [
        DocumentResponse(
            id=doc.id,
            filename=doc.filename,
            doc_number=doc.doc_number,
            doc_type=doc.doc_type,
            revision=doc.revision,
            title=doc.title,
            classification=doc.classification,
            page_count=doc.page_count,
            status=doc.status,
            created_at=doc.created_at,
        )
        for doc in docs
    ]


@router.delete("/{document_id}", status_code=204, response_model=None)
async def delete_document(
    document_id: UUID,
    tenant: Tenant = Depends(get_tenant),
) -> None:
    """Delete a document and all its chunks. Also removes the S3 object (non-dev)."""
    session_maker = tenant_session(tenant.schema_name)
    async with session_maker() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        s3_key = doc.s3_key

        # Delete from DB — chunks cascade via ON DELETE CASCADE
        await session.delete(doc)
        await session.commit()

    # Delete from S3 (skip in development — placeholder credentials)
    if settings.app_env != "development":
        try:
            s3 = boto3.client(
                "s3",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
            s3.delete_object(Bucket=settings.s3_bucket_name, Key=s3_key)
            logger.info(
                "documents.delete_s3",
                extra={"tenant": tenant.tenant_id, "s3_key": s3_key},
            )
        except Exception as exc:
            # Log but don't fail — DB row is already deleted
            logger.warning(
                "documents.delete_s3.failed",
                extra={"tenant": tenant.tenant_id, "s3_key": s3_key, "error": str(exc)},
            )

    logger.info(
        "documents.deleted",
        extra={"tenant": tenant.tenant_id, "document_id": str(document_id)},
    )
