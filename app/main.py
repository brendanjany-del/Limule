"""Point d'entrée de l'application Limule."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import async_engine, Base
from app.api.router import api_router
from app.api.dashboard import router as dashboard_router

# Importer tous les modèles pour que Base.metadata les connaisse
from app.models import specification, processing, data  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Crée les tables au démarrage (dev). En production, utiliser Alembic."""
    logger.info("Limule - Démarrage du pipeline bancaire réglementaire")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables créées / vérifiées")
    yield
    logger.info("Limule - Arrêt")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Pipeline de données bancaires réglementaires - Chargement, contrôle et export",
    lifespan=lifespan,
)

# Monter les fichiers statiques
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# API REST
app.include_router(api_router)

# Dashboard HTML
app.include_router(dashboard_router)
