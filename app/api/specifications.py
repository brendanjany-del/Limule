"""API endpoints pour la gestion des spécifications."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.specification import (
    SpecVersion, TechSpec, FieldSpec, FuncRule, RefValue,
    BusinessPerimeter, ExportSpec, TableName, FileFormat, DataType,
    RuleSeverity, ExportFormat,
)
from app.schemas.specification import (
    SpecVersionCreate, SpecVersionRead, VersionCopyRequest, SpecCopyFromVersionRequest,
    TechSpecCreate, TechSpecRead, FieldSpecCreate, FieldSpecRead,
    FuncRuleCreate, FuncRuleRead,
    RefValueCreate, RefValueBulkCreate, RefValueRead,
    BusinessPerimeterCreate, BusinessPerimeterRead, ExportSpecCreate,
)

router = APIRouter(prefix="/api/specifications", tags=["specifications"])


# ──────────────────────────────────────────────
# Versions
# ──────────────────────────────────────────────

@router.get("/versions", response_model=list[SpecVersionRead])
async def list_versions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SpecVersion).order_by(SpecVersion.created_at.desc()))
    return result.scalars().all()


@router.post("/versions", response_model=SpecVersionRead)
async def create_version(data: SpecVersionCreate, db: AsyncSession = Depends(get_db)):
    version = SpecVersion(**data.model_dump())
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


@router.get("/versions/{version_id}", response_model=SpecVersionRead)
async def get_version(version_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SpecVersion).where(SpecVersion.id == version_id))
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(404, "Version introuvable")
    return version


@router.post("/versions/copy", response_model=SpecVersionRead)
async def copy_version(data: VersionCopyRequest, db: AsyncSession = Depends(get_db)):
    """Copie les spécifications d'une version vers une nouvelle.

    Opération synchrone via le VersionManager (exécution en sync car copie en masse).
    """
    from app.core.versioning import VersionManager
    from app.database import SyncSessionLocal

    sync_db = SyncSessionLocal()
    try:
        vm = VersionManager(sync_db)
        target = vm.copy_version(
            source_code=data.source_code,
            target_code=data.target_code,
            target_label=data.target_label,
            include_tech=data.include_tech,
            include_func=data.include_func,
            include_ref=data.include_ref,
            include_business=data.include_business,
            metier_codes=data.metier_codes,
            description=data.description,
        )
        # Recharger en async
        result = await db.execute(select(SpecVersion).where(SpecVersion.code == data.target_code))
        return result.scalar_one()
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        sync_db.close()


@router.post("/versions/{version_id}/copy-spec")
async def copy_spec_from_version(version_id: int, data: SpecCopyFromVersionRequest,
                                  db: AsyncSession = Depends(get_db)):
    """Copie un type de spec depuis une autre version."""
    from app.core.versioning import VersionManager
    from app.database import SyncSessionLocal

    result = await db.execute(select(SpecVersion).where(SpecVersion.id == version_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "Version cible introuvable")

    sync_db = SyncSessionLocal()
    try:
        vm = VersionManager(sync_db)
        vm.copy_spec_from_version(target.code, data.source_version_code,
                                   data.spec_type, data.metier_code)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        sync_db.close()


# ──────────────────────────────────────────────
# Tech Specs
# ──────────────────────────────────────────────

@router.get("/versions/{version_id}/tech-specs", response_model=list[TechSpecRead])
async def list_tech_specs(version_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TechSpec)
        .where(TechSpec.version_id == version_id)
        .options(selectinload(TechSpec.fields))
    )
    return result.scalars().all()


@router.post("/tech-specs", response_model=TechSpecRead)
async def create_tech_spec(data: TechSpecCreate, db: AsyncSession = Depends(get_db)):
    fields_data = data.fields
    spec_data = data.model_dump(exclude={"fields"})
    spec_data["table_name"] = TableName(spec_data["table_name"])
    spec_data["file_format"] = FileFormat(spec_data["file_format"])

    spec = TechSpec(**spec_data)
    db.add(spec)
    await db.flush()

    for f in fields_data:
        field = FieldSpec(tech_spec_id=spec.id, **f.model_dump())
        field.data_type = DataType(field.data_type)
        db.add(field)

    await db.commit()

    result = await db.execute(
        select(TechSpec)
        .where(TechSpec.id == spec.id)
        .options(selectinload(TechSpec.fields))
    )
    return result.scalar_one()


@router.get("/tech-specs/{spec_id}", response_model=TechSpecRead)
async def get_tech_spec(spec_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TechSpec)
        .where(TechSpec.id == spec_id)
        .options(selectinload(TechSpec.fields))
    )
    spec = result.scalar_one_or_none()
    if not spec:
        raise HTTPException(404, "Spécification technique introuvable")
    return spec


@router.delete("/tech-specs/{spec_id}")
async def delete_tech_spec(spec_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TechSpec).where(TechSpec.id == spec_id))
    spec = result.scalar_one_or_none()
    if not spec:
        raise HTTPException(404, "Spécification technique introuvable")
    await db.delete(spec)
    await db.commit()
    return {"status": "deleted"}


# ──────────────────────────────────────────────
# Functional Rules
# ──────────────────────────────────────────────

@router.get("/versions/{version_id}/func-rules", response_model=list[FuncRuleRead])
async def list_func_rules(version_id: int, table_name: str = None,
                          db: AsyncSession = Depends(get_db)):
    query = select(FuncRule).where(FuncRule.version_id == version_id)
    if table_name:
        query = query.where(FuncRule.table_name == TableName(table_name))
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/func-rules", response_model=FuncRuleRead)
async def create_func_rule(data: FuncRuleCreate, db: AsyncSession = Depends(get_db)):
    rule_data = data.model_dump()
    rule_data["table_name"] = TableName(rule_data["table_name"])
    rule_data["severity"] = RuleSeverity(rule_data["severity"])
    rule = FuncRule(**rule_data)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.put("/func-rules/{rule_id}", response_model=FuncRuleRead)
async def update_func_rule(rule_id: int, data: FuncRuleCreate,
                           db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FuncRule).where(FuncRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Règle introuvable")
    for key, value in data.model_dump().items():
        if key == "table_name":
            value = TableName(value)
        elif key == "severity":
            value = RuleSeverity(value)
        setattr(rule, key, value)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/func-rules/{rule_id}")
async def delete_func_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FuncRule).where(FuncRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Règle introuvable")
    await db.delete(rule)
    await db.commit()
    return {"status": "deleted"}


# ──────────────────────────────────────────────
# Reference Values
# ──────────────────────────────────────────────

@router.get("/versions/{version_id}/ref-values")
async def list_ref_values(version_id: int, referentiel_code: str = None,
                          db: AsyncSession = Depends(get_db)):
    query = select(RefValue).where(RefValue.version_id == version_id)
    if referentiel_code:
        query = query.where(RefValue.referentiel_code == referentiel_code)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/ref-values", response_model=RefValueRead)
async def create_ref_value(data: RefValueCreate, db: AsyncSession = Depends(get_db)):
    ref = RefValue(**data.model_dump())
    db.add(ref)
    await db.commit()
    await db.refresh(ref)
    return ref


@router.post("/ref-values/bulk")
async def bulk_create_ref_values(data: RefValueBulkCreate, db: AsyncSession = Depends(get_db)):
    """Création en masse de valeurs de référentiel."""
    created = 0
    for v in data.values:
        ref = RefValue(
            version_id=data.version_id,
            referentiel_code=data.referentiel_code,
            value=v["value"],
            label=v.get("label"),
            is_active=v.get("is_active", True),
        )
        db.add(ref)
        created += 1
    await db.commit()
    return {"created": created}


# ──────────────────────────────────────────────
# Business Perimeters
# ──────────────────────────────────────────────

@router.get("/versions/{version_id}/perimeters", response_model=list[BusinessPerimeterRead])
async def list_perimeters(version_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BusinessPerimeter)
        .where(BusinessPerimeter.version_id == version_id)
        .options(selectinload(BusinessPerimeter.export_specs))
    )
    return result.scalars().all()


@router.post("/perimeters", response_model=BusinessPerimeterRead)
async def create_perimeter(data: BusinessPerimeterCreate, db: AsyncSession = Depends(get_db)):
    exports_data = data.export_specs
    perim_data = data.model_dump(exclude={"export_specs"})
    perim = BusinessPerimeter(**perim_data)
    db.add(perim)
    await db.flush()

    for e in exports_data:
        exp_data = e.model_dump()
        exp_data["table_name"] = TableName(exp_data["table_name"])
        exp_data["export_format"] = ExportFormat(exp_data["export_format"])
        exp = ExportSpec(perimeter_id=perim.id, **exp_data)
        db.add(exp)

    await db.commit()

    result = await db.execute(
        select(BusinessPerimeter)
        .where(BusinessPerimeter.id == perim.id)
        .options(selectinload(BusinessPerimeter.export_specs))
    )
    return result.scalar_one()


@router.delete("/perimeters/{perim_id}")
async def delete_perimeter(perim_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BusinessPerimeter).where(BusinessPerimeter.id == perim_id)
    )
    perim = result.scalar_one_or_none()
    if not perim:
        raise HTTPException(404, "Périmètre introuvable")
    await db.delete(perim)
    await db.commit()
    return {"status": "deleted"}
