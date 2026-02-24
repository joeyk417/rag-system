from __future__ import annotations

# TODO: implement in Task 6
# Pydantic v2 schemas:
#
# class TenantCreate(BaseModel):
#     tenant_id: str          # e.g. "elastomers_au"
#     name: str               # e.g. "Elastomers Australia"
#     api_key: str            # plaintext — stored as bcrypt hash
#     config: dict = {}       # tenant-specific config (parsing rules, restricted_doc_types, etc.)
#
# class TenantResponse(BaseModel):
#     id: UUID
#     tenant_id: str
#     name: str
#     schema_name: str
#     s3_prefix: str
#     config: dict
#     is_active: bool
#     created_at: datetime
