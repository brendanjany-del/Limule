"""Worker Celery pour les traitements asynchrones en arrière-plan."""

import logging

from celery import Celery

from app.config import settings
from app.database import SyncSessionLocal
from app.core.pipeline import Pipeline

logger = logging.getLogger(__name__)

celery_app = Celery(
    "limule",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Paris",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="process_flux", bind=True, max_retries=3)
def task_process_flux(self, flux_id: int):
    """Traite un flux en arrière-plan."""
    db = SyncSessionLocal()
    try:
        pipeline = Pipeline(db)
        pipeline.process_flux(flux_id)
        logger.info(f"Flux {flux_id} traité avec succès")
        return {"status": "success", "flux_id": flux_id}
    except Exception as e:
        logger.error(f"Erreur traitement flux {flux_id}: {e}")
        raise self.retry(exc=e, countdown=30)
    finally:
        db.close()


@celery_app.task(name="process_arrete", bind=True, max_retries=3)
def task_process_arrete(self, arrete_id: int):
    """Traite tous les flux d'un arrêté en arrière-plan."""
    db = SyncSessionLocal()
    try:
        pipeline = Pipeline(db)
        pipeline.process_arrete(arrete_id)
        logger.info(f"Arrêté {arrete_id} traité avec succès")
        return {"status": "success", "arrete_id": arrete_id}
    except Exception as e:
        logger.error(f"Erreur traitement arrêté {arrete_id}: {e}")
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()


@celery_app.task(name="export_arrete", bind=True, max_retries=3)
def task_export_arrete(self, arrete_id: int, perimeter_code: str = None):
    """Lance l'export d'un arrêté en arrière-plan."""
    db = SyncSessionLocal()
    try:
        pipeline = Pipeline(db)
        jobs = pipeline.export_arrete(arrete_id, perimeter_code)
        logger.info(f"Export arrêté {arrete_id}: {len(jobs)} jobs générés")
        return {"status": "success", "arrete_id": arrete_id, "jobs": len(jobs)}
    except Exception as e:
        logger.error(f"Erreur export arrêté {arrete_id}: {e}")
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()
