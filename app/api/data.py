"""API endpoints pour la consultation des données et rejets."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from app.database import get_db
from app.models.data import DataRow, RowStatus, Rejection
from app.models.processing import Flux, Arrete, Etablissement, ExportJob
from app.models.specification import SpecVersion, BusinessPerimeter
from app.schemas.processing import (
    DataRowRead, RejectionRead, DashboardStats, FluxSummary,
)

router = APIRouter(prefix="/api/data", tags=["data"])


# ──────────────────────────────────────────────
# Consultation des données
# ──────────────────────────────────────────────

@router.get("/rows", response_model=list[DataRowRead])
async def list_data_rows(
    flux_id: int,
    status: str = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Liste les lignes de données d'un flux avec filtres et pagination."""
    query = select(DataRow).where(DataRow.flux_id == flux_id)

    if status:
        query = query.where(DataRow.status == RowStatus(status))

    query = (
        query.order_by(DataRow.row_number)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/rows/count")
async def count_data_rows(
    flux_id: int,
    status: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Compte les lignes de données par statut."""
    query = select(func.count(DataRow.id)).where(DataRow.flux_id == flux_id)
    if status:
        query = query.where(DataRow.status == RowStatus(status))
    result = await db.execute(query)
    total = result.scalar()

    # Décompte par statut
    status_query = (
        select(DataRow.status, func.count(DataRow.id))
        .where(DataRow.flux_id == flux_id)
        .group_by(DataRow.status)
    )
    status_result = await db.execute(status_query)
    by_status = {str(row[0].value): row[1] for row in status_result.all()}

    return {"total": total, "by_status": by_status}


@router.get("/rows/{row_id}", response_model=DataRowRead)
async def get_data_row(row_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DataRow).where(DataRow.id == row_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Ligne introuvable")
    return row


# ──────────────────────────────────────────────
# Rejets
# ──────────────────────────────────────────────

@router.get("/rejections", response_model=list[RejectionRead])
async def list_rejections(
    flux_id: int = None,
    rejection_type: str = None,
    severity: str = None,
    rule_code: str = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Liste les rejets avec filtres."""
    query = select(Rejection)

    if flux_id:
        query = query.where(Rejection.flux_id == flux_id)
    if rejection_type:
        query = query.where(Rejection.rejection_type == rejection_type)
    if severity:
        query = query.where(Rejection.severity == severity)
    if rule_code:
        query = query.where(Rejection.rule_code == rule_code)

    query = (
        query.order_by(Rejection.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/rejections/summary")
async def rejection_summary(
    flux_id: int = None,
    arrete_id: int = None,
    db: AsyncSession = Depends(get_db),
):
    """Synthèse des rejets par type, sévérité et code de règle."""
    query = select(
        Rejection.rejection_type,
        Rejection.severity,
        Rejection.rule_code,
        func.count(Rejection.id).label("count"),
    )

    if flux_id:
        query = query.where(Rejection.flux_id == flux_id)
    elif arrete_id:
        flux_ids = select(Flux.id).where(Flux.arrete_id == arrete_id)
        query = query.where(Rejection.flux_id.in_(flux_ids))

    query = query.group_by(Rejection.rejection_type, Rejection.severity, Rejection.rule_code)
    result = await db.execute(query)

    return [
        {
            "rejection_type": row[0],
            "severity": row[1],
            "rule_code": row[2],
            "count": row[3],
        }
        for row in result.all()
    ]


# ──────────────────────────────────────────────
# Dashboard / Statistiques
# ──────────────────────────────────────────────

@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Statistiques globales du dashboard."""
    etab_count = await db.execute(select(func.count(Etablissement.id)))
    arrete_count = await db.execute(select(func.count(Arrete.id)))
    flux_count = await db.execute(select(func.count(Flux.id)))

    row_stats = await db.execute(
        select(
            func.coalesce(func.sum(Flux.total_lines), 0),
            func.coalesce(func.sum(Flux.valid_lines), 0),
            func.coalesce(func.sum(Flux.tech_rejected_lines), 0),
            func.coalesce(func.sum(Flux.func_rejected_lines), 0),
        )
    )
    stats = row_stats.one()

    export_count = await db.execute(
        select(func.count(ExportJob.id)).where(ExportJob.status == "success")
    )

    return DashboardStats(
        total_etablissements=etab_count.scalar() or 0,
        total_arretes=arrete_count.scalar() or 0,
        total_flux=flux_count.scalar() or 0,
        total_rows=stats[0] or 0,
        total_valid=stats[1] or 0,
        total_tech_rejected=stats[2] or 0,
        total_func_rejected=stats[3] or 0,
        total_exports=export_count.scalar() or 0,
    )


@router.get("/dashboard/flux-summary", response_model=list[FluxSummary])
async def flux_summary(
    etablissement_code: str = None,
    date_arrete: str = None,
    status: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Résumé de tous les flux avec informations contextuelles."""
    query = (
        select(
            Flux,
            Etablissement.code.label("etab_code"),
            Arrete.date_arrete,
            SpecVersion.code.label("version_code"),
        )
        .join(Arrete, Flux.arrete_id == Arrete.id)
        .join(Etablissement, Arrete.etablissement_id == Etablissement.id)
        .join(SpecVersion, Arrete.version_id == SpecVersion.id)
    )

    if etablissement_code:
        query = query.where(Etablissement.code == etablissement_code)
    if status:
        query = query.where(Flux.status == FluxStatus(status))

    query = query.order_by(Arrete.date_arrete.desc(), Flux.received_at.desc())
    result = await db.execute(query)

    summaries = []
    for row in result.all():
        flux = row[0]
        summaries.append(FluxSummary(
            flux_id=flux.id,
            file_name=flux.file_name,
            table_name=flux.table_name,
            status=flux.status.value if hasattr(flux.status, 'value') else str(flux.status),
            total_lines=flux.total_lines or 0,
            valid_lines=flux.valid_lines or 0,
            tech_rejected=flux.tech_rejected_lines or 0,
            func_rejected=flux.func_rejected_lines or 0,
            etablissement_code=row[1],
            date_arrete=row[2],
            version_code=row[3],
        ))

    return summaries
