from __future__ import annotations

import pytest

# TODO: add fixtures in Task 2+
# Planned fixtures:
#   test_db_session   → AsyncSession pointing at a test DB (separate schema, rolled back after each test)
#   test_client       → httpx.AsyncClient with ASGITransport(app=app)
#   ea_tenant         → pre-seeded EA tenant row in test DB
#   ea_api_key        → plaintext API key for ea_tenant
