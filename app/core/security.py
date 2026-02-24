from __future__ import annotations

# TODO: implement in Task 3
# verify_api_key(key: str, db: AsyncSession) -> Tenant
#   → hash key, query tenants table, raise 401 if not found or inactive
# verify_admin_key(key: str) -> None
#   → compare against settings.admin_api_key, raise 403 if mismatch
