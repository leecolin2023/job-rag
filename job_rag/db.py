from datetime import datetime, timezone
from pathlib import Path

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import Settings


def now():
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, index=True)
    job_id: Mapped[str] = mapped_column(String, index=True)
    raw: Mapped[dict] = mapped_column(JSON)
    normalized: Mapped[dict] = mapped_column(JSON)
    raw_hash: Mapped[str] = mapped_column(String)
    content_hash: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, default=1)
    indexed_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    index_signature: Mapped[str | None] = mapped_column(String, nullable=True)
    job_status: Mapped[str] = mapped_column(String, default="unknown", index=True)
    status_reason: Mapped[str] = mapped_column(Text, default="尚未核验招聘状态")
    first_seen_at: Mapped[str] = mapped_column(String)
    last_seen_at: Mapped[str] = mapped_column(String)
    last_verified_at: Mapped[str | None] = mapped_column(String, nullable=True)


class Revision(Base):
    __tablename__ = "revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_key: Mapped[str] = mapped_column(ForeignKey("jobs.key"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    raw: Mapped[dict] = mapped_column(JSON)
    normalized: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String)
    __table_args__ = (UniqueConstraint("job_key", "version"),)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_key: Mapped[str] = mapped_column(ForeignKey("jobs.key"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # PostgreSQL uses pgvector. SQLite stores vectors as JSON for the small-data fallback.
    embedding: Mapped[list | None] = mapped_column(JSON().with_variant(Vector(), "postgresql"), nullable=True)
    __table_args__ = (UniqueConstraint("job_key", "version", "ordinal"),)


class IndexTask(Base):
    __tablename__ = "index_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_key: Mapped[str] = mapped_column(ForeignKey("jobs.key"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    signature: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String)
    __table_args__ = (UniqueConstraint("job_key", "version", "signature"),)


class StatusEvent(Base):
    __tablename__ = "status_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_key: Mapped[str] = mapped_column(ForeignKey("jobs.key"), index=True)
    old_status: Mapped[str] = mapped_column(String)
    new_status: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String)


class Database:
    def __init__(self, settings: Settings):
        if settings.database_url.startswith("sqlite:///"):
            path = settings.database_url.removeprefix("sqlite:///")
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
        kwargs = {"connect_args": {"check_same_thread": False, "timeout": 30}} if settings.database_url.startswith("sqlite") else {}
        self.engine = create_engine(settings.database_url, **kwargs)
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine, "connect")
            def configure_sqlite(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self):
        inspector = inspect(self.engine)
        if inspector.has_table("chunks") and "details" not in {column["name"] for column in inspector.get_columns("chunks")}:
            raise ValueError("Database schema requires migration. Back up first, then run: job-rag migrate")
        if self.engine.dialect.name == "postgresql":
            with self.engine.begin() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(self.engine)

    def migrate(self):
        """Explicit, additive migration; preserves raw records and existing index data."""
        with self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(89733021)"))
            elif self.engine.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            inspector = inspect(connection)
            connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (name VARCHAR(100) PRIMARY KEY, applied_at VARCHAR(100) NOT NULL)"))
            if inspector.has_table("chunks") and "details" not in {column["name"] for column in inspector.get_columns("chunks")}:
                connection.execute(text("ALTER TABLE chunks ADD COLUMN details JSON"))
            found = connection.scalar(text("SELECT name FROM schema_migrations WHERE name = '002_chunk_structure'"))
            if not found:
                connection.execute(text("INSERT INTO schema_migrations (name, applied_at) VALUES (:name, :at)"),
                                   {"name": "002_chunk_structure", "at": now()})
        self.initialize()
        return {"ok": True, "migration": "002_chunk_structure", "reindex_required": True}
