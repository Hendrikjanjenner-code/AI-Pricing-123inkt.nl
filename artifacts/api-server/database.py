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

# Achtergrondtaken (feed-sync, modelrun) verwerken tienduizenden rijen per
# DELETE/INSERT. De strakke request-timeout van 4s is daarvoor veel te kort en
# breekt de sync (zie feed_ingest: per-dag delete van honderdduizenden
# concurrentprijzen). Deze sessies krijgen daarom een ruime timeout via een
# APARTE engine/pool, zodat de 4s-bescherming op gebruikersverzoeken intact
# blijft en de lange timeout NOOIT via een pool-verbinding naar een request lekt.
DB_BACKGROUND_STATEMENT_TIMEOUT_MS = int(
    os.environ.get("DB_BACKGROUND_STATEMENT_TIMEOUT_MS", "600000")  # 10 min
)

# SQLAlchemy uses psycopg2 dialect
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": DB_CONNECT_TIMEOUT_SECONDS,
        "options": f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS}",
    },
)

# Aparte engine met ruime statement-timeout, uitsluitend voor achtergrondtaken.
# Kleine pool: er draait maar één sync tegelijk.
background_engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=1,
    max_overflow=2,
    connect_args={
        "connect_timeout": DB_CONNECT_TIMEOUT_SECONDS,
        "options": f"-c statement_timeout={DB_BACKGROUND_STATEMENT_TIMEOUT_MS}",
    },
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Sessiefabriek voor achtergrondtaken (feed-sync/modelrun). Gebruik deze i.p.v.
# SessionLocal voor bulk-verwerking, zie DB_BACKGROUND_STATEMENT_TIMEOUT_MS.
BackgroundSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=background_engine
)

Base = declarative_base()


def get_db():
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
