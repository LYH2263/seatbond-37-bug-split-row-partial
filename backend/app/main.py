from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty

# Columns added after the initial baseline: create_all() never alters existing
# tables, so patch them in place (idempotent).
_COLUMN_PATCHES = {
    "halls": {
        "blocked_seats": "VARCHAR(400) NOT NULL DEFAULT ''",
        "frozen": "BOOLEAN NOT NULL DEFAULT FALSE",
    },
    "seat_holds": {
        "segment_no": "INTEGER NOT NULL DEFAULT 1",
    },
}


def _ensure_column_patches() -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _COLUMN_PATCHES.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_column_patches()
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="SeatBond", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
