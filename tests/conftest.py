import pytest
from fastapi.testclient import TestClient

from backend import database as db
from backend.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "complaint-compass-test.db")
    with TestClient(app) as test_client:
        yield test_client
