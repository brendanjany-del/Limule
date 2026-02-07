"""Configuration de la connexion à la base de données.

Supporte PostgreSQL (production) et SQLite (développement / preview).
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# Moteur async (pour FastAPI)
_async_kwargs = {"echo": settings.DEBUG}
if not _is_sqlite:
    _async_kwargs.update(pool_size=20, max_overflow=10, pool_pre_ping=True)

async_engine = create_async_engine(settings.DATABASE_URL, **_async_kwargs)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Moteur sync (pour Celery workers / pipeline)
_sync_kwargs = {"echo": settings.DEBUG}
if not _is_sqlite:
    _sync_kwargs.update(pool_size=20, max_overflow=10, pool_pre_ping=True)

sync_engine = create_engine(settings.DATABASE_URL_SYNC, **_sync_kwargs)

SyncSessionLocal = sessionmaker(bind=sync_engine)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_sync_db():
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()
