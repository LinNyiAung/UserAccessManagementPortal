import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL=f"sqlite:///{_tmp}/test.db",
    KEYS_DIR=f"{_tmp}/keys",
    ISSUER="http://testserver",
    FRONTEND_URL="http://testserver",
    ADMIN_USERNAME="admin",
    ADMIN_PASSWORD="test-admin-pass",
    FRONTEND_DIST=f"{_tmp}/no-dist",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
