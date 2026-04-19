"""
DB Factory — reads STORAGE_BACKEND from env and returns the right client handle.

All DB services import from here rather than reading the env directly.
Decision D-2: create_all() for local SQLite; Alembic upgrade head for cloud PostgreSQL.
Decision D-3: startup pings warn but do not crash the server.
"""

import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger("deckr.db_factory")

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()
DB_URL = os.getenv("DB_URL", "sqlite:///./data/deckr.db")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "deckr")
NEO4J_URL = os.getenv("NEO4J_URL", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


# ---------------------------------------------------------------------------
# SQL — SQLAlchemy engine + session factory
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_sql_engine():
    """Return the SQLAlchemy engine. Created once and reused."""
    from sqlalchemy import create_engine

    connect_args = {}
    if DB_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Ensure the data/ directory exists before SQLite tries to create the file
        db_path = DB_URL.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    engine = create_engine(DB_URL, connect_args=connect_args, echo=False)
    logger.info("SQL engine created: %s", DB_URL.split("@")[-1])  # mask credentials
    return engine


def init_sql_schema():
    """
    D-2: create_all() for local SQLite (zero-migration startup).
    For PostgreSQL/cloud, use Alembic: `alembic upgrade head`.
    """
    from models.sql_models import Base
    engine = get_sql_engine()
    Base.metadata.create_all(engine)
    logger.info("SQL schema initialised (create_all)")


def get_sql_session():
    """Yield a SQLAlchemy Session. Use as a context manager."""
    from sqlalchemy.orm import Session
    engine = get_sql_engine()
    with Session(engine) as session:
        yield session


def atomic_session():
    """
    Return a context manager that yields a single SQLAlchemy Session with one
    committed transaction. Rolls back automatically on any exception.

    Usage:
        with atomic_session() as session:
            session.add(obj)
            # commit happens automatically on clean exit
    """
    from contextlib import contextmanager
    from sqlalchemy.orm import Session

    @contextmanager
    def _ctx():
        engine = get_sql_engine()
        with Session(engine) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    return _ctx()


def ping_sql() -> bool:
    """D-3: warn on failure, don't crash."""
    try:
        from sqlalchemy import text
        engine = get_sql_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("SQL ping failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# MongoDB — pymongo client
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_mongo_client():
    """Return a pymongo MongoClient. Created once and reused."""
    try:
        import pymongo
        client = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
        logger.info("MongoDB client created: %s", MONGO_URL.split("@")[-1])
        return client
    except ImportError:
        logger.warning("pymongo not installed — MongoDB unavailable")
        return None


def get_mongo_db():
    """Return the configured MongoDB database handle, or None if unavailable."""
    client = get_mongo_client()
    if client is None:
        return None
    return client[MONGO_DB_NAME]


def ping_mongo() -> bool:
    """D-3: warn on failure, don't crash."""
    try:
        client = get_mongo_client()
        if client is None:
            return False
        client.admin.command("ping")
        return True
    except Exception as exc:
        logger.warning("MongoDB ping failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Neo4j — Bolt driver
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_neo4j_driver():
    """Return a Neo4j driver, or None if neo4j package is missing or creds are absent."""
    if not NEO4J_PASSWORD:
        logger.warning("NEO4J_PASSWORD not set — Neo4j unavailable")
        return None
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASSWORD))
        logger.info("Neo4j driver created: %s", NEO4J_URL)
        return driver
    except ImportError:
        logger.warning("neo4j driver not installed — graph tier unavailable")
        return None


def ping_neo4j() -> bool:
    """D-3: warn on failure, don't crash."""
    try:
        driver = get_neo4j_driver()
        if driver is None:
            return False
        with driver.session() as session:
            session.run("RETURN 1")
        return True
    except Exception as exc:
        logger.warning("Neo4j ping failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Health summary — consumed by /api/health
# ---------------------------------------------------------------------------

def db_health() -> dict[str, Any]:
    """
    Returns per-tier connectivity status and the active storage backend.
    Called during /api/health — runs pings inline (fast path; each ping has a short timeout).
    """
    return {
        "storage_backend": STORAGE_BACKEND,
        "sql": {"url_scheme": DB_URL.split(":")[0], "connected": ping_sql()},
        "mongo": {"connected": ping_mongo()},
        "neo4j": {"connected": ping_neo4j()},
    }
