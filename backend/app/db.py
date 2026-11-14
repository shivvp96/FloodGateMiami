import os
from collections.abc import Generator

from sqlmodel import SQLModel, Session, create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")

# Local development default (preserved)
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./floodguard_miami.db"

is_sqlite = DATABASE_URL.startswith("sqlite://")

# On production platforms, SQLite-on-disk would be ephemeral; fail fast instead.
# Use APP_ENV as the primary switch; fall back to Vercel env detection for compatibility.
app_env = os.environ.get("APP_ENV", "development").lower()
is_production = app_env in {"production", "staging"}

if (is_production or os.environ.get("VERCEL") or os.environ.get("Vercel")) and is_sqlite:
    raise RuntimeError(
        "Refusing to run in production/staging with SQLite. Provide a persistent DATABASE_URL (e.g. Postgres)."
    )

connect_args = {"check_same_thread": False} if is_sqlite else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


def _column_exists(session: Session, table: str, column: str) -> bool:
    if DATABASE_URL.startswith("sqlite://"):
        row = session.exec(
            text(f"SELECT COUNT(*) FROM pragma_table_info('{table}') WHERE name = :column"),
            params={"column": column},
        ).one()
        return bool(row[0])
    row = session.exec(
        text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        params={"table": table, "column": column},
    ).one()
    return bool(row[0])


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    # Safe additive migration: add latitude/longitude columns to pre-existing rows.
    # create_all does not alter existing tables, so patch manually and idempotently.
    with Session(engine) as session:
        for column in ("latitude", "longitude"):
            if not _column_exists(session, "savedlocation", column):
                session.exec(text(f"ALTER TABLE savedlocation ADD COLUMN {column} DOUBLE PRECISION"))
        if not _column_exists(session, "savedlocation", "user_id"):
            session.exec(text("ALTER TABLE savedlocation ADD COLUMN user_id VARCHAR(36)"))
        session.commit()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
