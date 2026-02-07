"""Configuration de l'application Limule."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings

_db_path = Path(__file__).parent.parent / "limule.db"


class Settings(BaseSettings):
    APP_NAME: str = "Limule"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Base de données (SQLite par défaut pour dev, PostgreSQL en production)
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{_db_path}",
    )
    DATABASE_URL_SYNC: str = os.environ.get(
        "DATABASE_URL_SYNC",
        f"sqlite:///{_db_path}",
    )

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"

    # Répertoires de données
    DATA_INPUT_DIR: str = str(Path(__file__).parent.parent / "data" / "input")
    DATA_OUTPUT_DIR: str = str(Path(__file__).parent.parent / "data" / "output")

    # Chargement
    BATCH_SIZE: int = 50_000  # Taille du batch pour le chargement en BDD
    MAX_WORKERS: int = 4      # Nombre de workers parallèles

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
