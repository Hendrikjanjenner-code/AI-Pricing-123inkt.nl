"""
SQLAlchemy database engine and session setup.
Uses DATABASE_URL from environment (Replit-managed PostgreSQL).
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set.")

# How long (seconds) to wait when establishing a brand-new TCP/libpq
# connection to Postgres before giving up. Without this, an unreachable or
# firewalled database can hang the psycopg2 connect() call indefinitely,
# which in turn hangs any request (e.g. login) that needs a DB connection.
DB_CONNECT_TIMEOUT_SECONDS = int(os.environ.get("DB_CONNECT_TIMEOUT_SECONDS", "3"))

# How long (seconds) a single statement is allowed to run on the server
# before Postgres itself cancels it. Guards against a slow query hanging a
# request even once the connection is established. Applied via libpq
# `options` so it takes effect for every statement on every connection from
# this pool.
DB_STATEMENT_TIMEOUT_MS = int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "4000"))

# SQLAlchemy uses psycopg2 dialect
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": DB_CONNECT_TIMEOUT_SECONDS,
        "options": f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS}",
    },
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
