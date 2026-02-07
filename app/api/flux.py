"""API endpoints pour la gestion des flux et du pipeline."""

import shutil
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db, SyncSessionLocal
from app.models.processing import (
    Etablissement, Arrete, Flux, FluxStatus, ProcessingStep, ExportJob,
)
from app.models.specification import SpecVersion
from app.schemas.processing import (
    EtablissementCreate, EtablissementRead,
    ArreteRead, ArreteDetailRead, FluxRead, ProcessingStepRead,
    ExportJobRead, ExportRequest,
)
from app.core.pipeline import Pipeline
from app.config import settings

router = APIRouter(prefix="/api", tags=["flux"])


# ──────────────────────────────────────────────
# Établissements
# ──────────────────────────────────────────────

@router.get("/etablissements", response_model=list[EtablissementRead])
async def list_etablissements(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Etablissement).order_by(Etablissement.code))
    return result.scalars().all()


@router.post("/etablissements", response_model=EtablissementRead)
async def create_etablissement(data: EtablissementCreate, db: AsyncSession = Depends(get_db)):
    etab = Etablissement(**data.model_dump())
    db.add(etab)
    await db.commit()
    await db.refresh(etab)
    return etab


# ──────────────────────────────────────────────
# Arrêtés
# ──────────────────────────────────────────────

@router.get("/arretes", response_model=list[ArreteRead])
async def list_arretes(etablissement_id: int = None, db: AsyncSession = Depends(get_db)):
    query = select(Arrete).order_by(Arrete.date_arrete.desc())
    if etablissement_id:
        query = query.where(Arrete.etablissement_id == etablissement_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/arretes/{arrete_id}", response_model=ArreteDetailRead)
async def get_arrete(arrete_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Arrete)
        .where(Arrete.id == arrete_id)
        .options(
            selectinload(Arrete.etablissement),
            selectinload(Arrete.flux),
        )
    )
    arrete = result.scalar_one_or_none()
    if not arrete:
        raise HTTPException(404, "Arrêté introuvable")
    return arrete


# ──────────────────────────────────────────────
# Upload et réception de flux
# ──────────────────────────────────────────────

@router.post("/flux/upload", response_model=FluxRead)
async def upload_flux(
    file: UploadFile = File(...),
    etablissement_code: str = Form(...),
    date_arrete: date = Form(...),
    table_name: str = Form(...),
    version_code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload un fichier de données et l'enregistre comme flux."""
    # Sauvegarder le fichier
    input_dir = Path(settings.DATA_INPUT_DIR)
    input_dir.mkdir(parents=True, exist_ok=True)
    file_path = input_dir / file.filename

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Enregistrer via le pipeline (sync car SQLAlchemy sync dans pipeline)
    sync_db = SyncSessionLocal()
    try:
        pipeline = Pipeline(sync_db)
        flux = pipeline.receive_file(
            file_path=str(file_path),
            file_name=file.filename,
            etablissement_code=etablissement_code,
            date_arrete=date_arrete,
            table_name=table_name,
            version_code=version_code,
        )
        flux_id = flux.id
    finally:
        sync_db.close()

    # Recharger en async
    result = await db.execute(select(Flux).where(Flux.id == flux_id))
    return result.scalar_one()


@router.post("/flux/upload-auto", response_model=FluxRead)
async def upload_flux_auto(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload un fichier et déduit automatiquement les métadonnées du nom."""
    from app.core.pipeline import Pipeline

    input_dir = Path(settings.DATA_INPUT_DIR)
    input_dir.mkdir(parents=True, exist_ok=True)
    file_path = input_dir / file.filename

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    sync_db = SyncSessionLocal()
    try:
        pipeline = Pipeline(sync_db)
        parsed = pipeline.parse_file_name(file.filename)
        if not parsed:
            raise HTTPException(
                400,
                "Impossible de parser le nom du fichier. "
                "Format attendu: {version}_{etablissement}_{YYYYMM}_{table}.ext"
            )

        flux = pipeline.receive_file(
            file_path=str(file_path),
            file_name=file.filename,
            **parsed,
        )
        flux_id = flux.id
    finally:
        sync_db.close()

    result = await db.execute(select(Flux).where(Flux.id == flux_id))
    return result.scalar_one()


# ──────────────────────────────────────────────
# Traitement des flux
# ──────────────────────────────────────────────

@router.post("/flux/{flux_id}/process", response_model=FluxRead)
async def process_flux(flux_id: int, db: AsyncSession = Depends(get_db)):
    """Lance le traitement complet d'un flux (chargement + validations)."""
    sync_db = SyncSessionLocal()
    try:
        pipeline = Pipeline(sync_db)
        pipeline.process_flux(flux_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur de traitement: {str(e)}")
    finally:
        sync_db.close()

    result = await db.execute(select(Flux).where(Flux.id == flux_id))
    flux = result.scalar_one_or_none()
    if not flux:
        raise HTTPException(404, "Flux introuvable")
    return flux


@router.post("/arretes/{arrete_id}/process")
async def process_arrete(arrete_id: int, db: AsyncSession = Depends(get_db)):
    """Lance le traitement complet de tous les flux d'un arrêté."""
    sync_db = SyncSessionLocal()
    try:
        pipeline = Pipeline(sync_db)
        pipeline.process_arrete(arrete_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        sync_db.close()

    result = await db.execute(
        select(Arrete).where(Arrete.id == arrete_id)
        .options(selectinload(Arrete.flux))
    )
    arrete = result.scalar_one_or_none()
    if not arrete:
        raise HTTPException(404, "Arrêté introuvable")
    return ArreteDetailRead.model_validate(arrete)


# ──────────────────────────────────────────────
# Suivi du pipeline
# ──────────────────────────────────────────────

@router.get("/flux/{flux_id}", response_model=FluxRead)
async def get_flux(flux_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Flux).where(Flux.id == flux_id))
    flux = result.scalar_one_or_none()
    if not flux:
        raise HTTPException(404, "Flux introuvable")
    return flux


@router.get("/flux/{flux_id}/steps", response_model=list[ProcessingStepRead])
async def get_flux_steps(flux_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProcessingStep)
        .where(ProcessingStep.flux_id == flux_id)
        .order_by(ProcessingStep.started_at)
    )
    return result.scalars().all()


# ──────────────────────────────────────────────
# Exports
# ──────────────────────────────────────────────

@router.post("/exports", response_model=list[ExportJobRead])
async def run_export(data: ExportRequest, db: AsyncSession = Depends(get_db)):
    """Lance l'export des données d'un arrêté pour un périmètre métier."""
    sync_db = SyncSessionLocal()
    try:
        pipeline = Pipeline(sync_db)
        jobs = pipeline.export_arrete(data.arrete_id, data.perimeter_code)
        job_ids = [j.id for j in jobs]
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        sync_db.close()

    result = await db.execute(
        select(ExportJob).where(ExportJob.id.in_(job_ids))
    )
    return result.scalars().all()


@router.get("/arretes/{arrete_id}/exports", response_model=list[ExportJobRead])
async def list_exports(arrete_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ExportJob)
        .where(ExportJob.arrete_id == arrete_id)
        .order_by(ExportJob.started_at.desc())
    )
    return result.scalars().all()
