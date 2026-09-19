import os

# 强制测试走内存 SQLite，与 docker 里的 Postgres 完全隔离（须在 import app 前设置）。
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

_test_engine = create_engine(
    "sqlite+pysqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db():
    Base.metadata.drop_all(_test_engine)
    Base.metadata.create_all(_test_engine)
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()
