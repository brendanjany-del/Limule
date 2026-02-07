"""Configuration de l'application Limule."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Limule"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Base de données
    DATABASE_URL: str = "postgresql+asyncpg://limule:limule_secret@localhost:5432/limule"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://limule:limule_secret@localhost:5432/limule"

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
