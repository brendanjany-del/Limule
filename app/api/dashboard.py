"""Routes du dashboard (pages HTML servies par Jinja2)."""

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.processing import Etablissement, Arrete, Flux, ExportJob
from app.models.specification import SpecVersion, BusinessPerimeter
from app.models.data import DataRow, RowStatus, Rejection

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["dashboard"])


@router.get("/")
async def dashboard_home(request: Request, db: AsyncSession = Depends(get_db)):
    """Page d'accueil du dashboard."""
    # Stats globales
    etab_count = (await db.execute(select(func.count(Etablissement.id)))).scalar() or 0
    arrete_count = (await db.execute(select(func.count(Arrete.id)))).scalar() or 0
    flux_count = (await db.execute(select(func.count(Flux.id)))).scalar() or 0

    row_stats = (await db.execute(select(
        func.coalesce(func.sum(Flux.total_lines), 0),
        func.coalesce(func.sum(Flux.valid_lines), 0),
        func.coalesce(func.sum(Flux.tech_rejected_lines), 0),
        func.coalesce(func.sum(Flux.func_rejected_lines), 0),
    ))).one()

    export_count = (await db.execute(
        select(func.count(ExportJob.id)).where(ExportJob.status == "success")
    )).scalar() or 0

    # Derniers flux
    recent_flux = (await db.execute(
        select(Flux)
        .order_by(Flux.received_at.desc())
        .limit(10)
    )).scalars().all()

    # Arrêtés récents
    recent_arretes = (await db.execute(
        select(Arrete)
        .options(selectinload(Arrete.etablissement))
        .order_by(Arrete.date_arrete.desc())
        .limit(10)
    )).scalars().all()

    return templates.TemplateResponse("dashboard/index.html", {
        "request": request,
        "stats": {
            "etablissements": etab_count,
            "arretes": arrete_count,
            "flux": flux_count,
            "total_rows": row_stats[0],
            "valid_rows": row_stats[1],
            "tech_rejected": row_stats[2],
            "func_rejected": row_stats[3],
            "exports": export_count,
        },
        "recent_flux": recent_flux,
        "recent_arretes": recent_arretes,
    })


@router.get("/processing")
async def processing_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Page de suivi des traitements."""
    etablissements = (await db.execute(
        select(Etablissement).order_by(Etablissement.code)
    )).scalars().all()

    arretes = (await db.execute(
        select(Arrete)
        .options(
            selectinload(Arrete.etablissement),
            selectinload(Arrete.flux),
            selectinload(Arrete.version),
        )
        .order_by(Arrete.date_arrete.desc())
    )).scalars().all()

    return templates.TemplateResponse("dashboard/processing.html", {
        "request": request,
        "etablissements": etablissements,
        "arretes": arretes,
    })


@router.get("/data-viewer")
async def data_viewer_page(
    request: Request,
    flux_id: int = None,
    status: str = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    """Page de visualisation des données."""
    flux_list = (await db.execute(
        select(Flux).order_by(Flux.received_at.desc())
    )).scalars().all()

    rows = []
    total = 0
    selected_flux = None
    page_size = 50

    if flux_id:
        selected_flux = (await db.execute(
            select(Flux).where(Flux.id == flux_id)
        )).scalar_one_or_none()

        query = select(DataRow).where(DataRow.flux_id == flux_id)
        if status:
            query = query.where(DataRow.status == RowStatus(status))
        total_q = select(func.count(DataRow.id)).where(DataRow.flux_id == flux_id)
        if status:
            total_q = total_q.where(DataRow.status == RowStatus(status))
        total = (await db.execute(total_q)).scalar() or 0

        query = query.order_by(DataRow.row_number).offset((page - 1) * page_size).limit(page_size)
        rows = (await db.execute(query)).scalars().all()

    return templates.TemplateResponse("dashboard/data_viewer.html", {
        "request": request,
        "flux_list": flux_list,
        "selected_flux": selected_flux,
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "status_filter": status,
        "flux_id": flux_id,
    })


@router.get("/rejections")
async def rejections_page(
    request: Request,
    flux_id: int = None,
    rejection_type: str = None,
    severity: str = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    """Page de visualisation des rejets."""
    flux_list = (await db.execute(
        select(Flux).order_by(Flux.received_at.desc())
    )).scalars().all()

    rejections = []
    total = 0
    page_size = 50

    query = select(Rejection)
    count_query = select(func.count(Rejection.id))

    if flux_id:
        query = query.where(Rejection.flux_id == flux_id)
        count_query = count_query.where(Rejection.flux_id == flux_id)
    if rejection_type:
        query = query.where(Rejection.rejection_type == rejection_type)
        count_query = count_query.where(Rejection.rejection_type == rejection_type)
    if severity:
        query = query.where(Rejection.severity == severity)
        count_query = count_query.where(Rejection.severity == severity)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(Rejection.id).offset((page - 1) * page_size).limit(page_size)
    rejections = (await db.execute(query)).scalars().all()

    # Synthèse par règle
    summary_query = (
        select(
            Rejection.rejection_type,
            Rejection.rule_code,
            Rejection.severity,
            func.count(Rejection.id),
        )
        .group_by(Rejection.rejection_type, Rejection.rule_code, Rejection.severity)
    )
    if flux_id:
        summary_query = summary_query.where(Rejection.flux_id == flux_id)
    summary = (await db.execute(summary_query)).all()

    return templates.TemplateResponse("dashboard/rejections.html", {
        "request": request,
        "flux_list": flux_list,
        "rejections": rejections,
        "total": total,
        "page": page,
        "page_size": page_size,
        "flux_id": flux_id,
        "rejection_type": rejection_type,
        "severity": severity,
        "summary": summary,
    })


@router.get("/specifications")
async def specifications_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Page de gestion des spécifications."""
    versions = (await db.execute(
        select(SpecVersion).order_by(SpecVersion.created_at.desc())
    )).scalars().all()

    return templates.TemplateResponse("dashboard/specifications.html", {
        "request": request,
        "versions": versions,
    })


@router.get("/exports")
async def exports_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Page de suivi des exports."""
    jobs = (await db.execute(
        select(ExportJob)
        .options(
            selectinload(ExportJob.arrete).selectinload(Arrete.etablissement),
            selectinload(ExportJob.perimeter),
        )
        .order_by(ExportJob.started_at.desc())
    )).scalars().all()

    arretes = (await db.execute(
        select(Arrete)
        .options(selectinload(Arrete.etablissement))
        .order_by(Arrete.date_arrete.desc())
    )).scalars().all()

    return templates.TemplateResponse("dashboard/exports.html", {
        "request": request,
        "jobs": jobs,
        "arretes": arretes,
    })
