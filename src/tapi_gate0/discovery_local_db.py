"""Validate A5 database targets without creating a SQLite database."""
from pathlib import Path

from sqlalchemy.engine import make_url


def validate_existing_database_url(raw: str) -> str:
    if not raw.startswith(("sqlite:///", "postgresql+psycopg://")):
        raise ValueError("INVALID_DATABASE_URL")
    url = make_url(raw)
    if url.drivername == "sqlite":
        # Plain filesystem SQLite only, not URI mode or in-memory databases.
        if not url.database or url.database == ":memory:" or url.query:
            raise ValueError("DATABASE_MUST_EXIST")
        path = Path(url.database)
        if not path.is_file():
            raise ValueError("DATABASE_MUST_EXIST")
    return raw
