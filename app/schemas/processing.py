"""Schemas Pydantic pour le traitement et le suivi."""

from datetime import datetime, date
from pydantic import BaseModel


class EtablissementCreate(BaseModel):
    code: str
    name: str
    reseau_code: str | None = None


class EtablissementRead(BaseModel):
    id: int
    code: str
    name: str
    reseau_code: str | None
    is_active: bool
    model_config = {"from_attributes": True}


class FluxRead(BaseModel):
    id: int
    arrete_id: int
    table_name: str
    file_name: str
    status: str
    total_lines: int
    loaded_lines: int
    valid_lines: int
    tech_rejected_lines: int
    func_rejected_lines: int
    warning_lines: int
    error_message: str | None
    received_at: datetime | None
    processed_at: datetime | None
    model_config = {"from_attributes": True}


class ProcessingStepRead(BaseModel):
    id: int
    flux_id: int
    step_type: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    records_processed: int
    records_ok: int
    records_rejected: int
    records_warning: int
    error_message: str | None
    model_config = {"from_attributes": True}


class ArreteRead(BaseModel):
    id: int
    date_arrete: date
    etablissement_id: int
    version_id: int
    status: str
    created_at: datetime | None
    model_config = {"from_attributes": True}


class ArreteDetailRead(ArreteRead):
    etablissement: EtablissementRead | None = None
    flux: list[FluxRead] = []


class FluxUploadRequest(BaseModel):
    etablissement_code: str
    date_arrete: date
    table_name: str
    version_code: str


class ExportJobRead(BaseModel):
    id: int
    arrete_id: int
    perimeter_id: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    output_files: list | None
    total_records: int
    error_message: str | None
    model_config = {"from_attributes": True}


class ExportRequest(BaseModel):
    arrete_id: int
    perimeter_code: str | None = None


# ── Dashboard schemas ──

class DashboardStats(BaseModel):
    total_etablissements: int
    total_arretes: int
    total_flux: int
    total_rows: int
    total_valid: int
    total_tech_rejected: int
    total_func_rejected: int
    total_exports: int


class FluxSummary(BaseModel):
    flux_id: int
    file_name: str
    table_name: str
    status: str
    total_lines: int
    valid_lines: int
    tech_rejected: int
    func_rejected: int
    etablissement_code: str
    date_arrete: date
    version_code: str


class RejectionRead(BaseModel):
    id: int
    data_row_id: int
    flux_id: int
    rejection_type: str
    rule_code: str | None
    field_name: str | None
    field_value: str | None
    expected: str | None
    message: str
    severity: str
    model_config = {"from_attributes": True}


class DataRowRead(BaseModel):
    id: int
    flux_id: int
    table_name: str
    row_number: int
    data: dict
    business_key: str | None
    status: str
    model_config = {"from_attributes": True}
