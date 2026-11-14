import os
from collections.abc import Generator

from sqlmodel import SQLModel, Session, create_engine

DATABASE_URL = os.environ.get("DATABASE_URL")

# Local development default (preserved)
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./floodguard_miami.db"

is_sqlite = DATABASE_URL.startswith("sqlite://")

# On production platforms, SQLite-on-disk would be ephemeral; fail fast instead.
# Use APP_ENV as the primary switch; fall back to Vercel env detection for compatibility.
app_env = os.environ.get("APP_ENV", "development").lower()
is_production = app_env in {"production", "staging"}

if (is_production or os.environ.get("VERCEL") or os.environ.get("Vercel")) and not is_sqlite:
    # Postgres/other supported drivers should work with DATABASE_URL.
    pass

if (is_production or os.environ.get("VERCEL") or os.environ.get("Vercel")) and is_sqlite:
    raise RuntimeError(
        "Refusing to run in production/staging with SQLite. Provide a persistent DATABASE_URL (e.g. Postgres)."
    )

connect_args = {"check_same_thread": False} if is_sqlite else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
