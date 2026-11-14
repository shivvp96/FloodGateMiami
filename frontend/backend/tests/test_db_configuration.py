import importlib
import os

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.main import create_app


def test_vercel_with_sqlite_database_url_fails_fast() -> None:
    os.environ["VERCEL"] = "1"
    os.environ["DATABASE_URL"] = "sqlite:///./should-not-run-on-vercel.db"

    import app.db as db_module

    with pytest.raises(RuntimeError):
        importlib.reload(db_module)

    os.environ.pop("VERCEL", None)
    os.environ.pop("DATABASE_URL", None)


def test_health_works_with_default_local_sqlite() -> None:
    os.environ.pop("VERCEL", None)
    os.environ.pop("DATABASE_URL", None)

    import app.db as db_module

    SQLModel.metadata.drop_all(db_module.engine)
    SQLModel.metadata.create_all(db_module.engine)

    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
