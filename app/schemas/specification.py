"""Schemas Pydantic pour les spécifications."""

from datetime import datetime
from pydantic import BaseModel, Field


# ── Version ──

class SpecVersionCreate(BaseModel):
    code: str = Field(..., max_length=50)
    label: str = Field(..., max_length=200)
    description: str | None = None
    created_by: str | None = None


class SpecVersionRead(BaseModel):
    id: int
    code: str
    label: str
    description: str | None
    is_active: bool
    created_at: datetime | None
    created_by: str | None
    model_config = {"from_attributes": True}


class VersionCopyRequest(BaseModel):
    source_code: str
    target_code: str
    target_label: str
    description: str | None = None
    include_tech: bool = True
    include_func: bool = True
    include_ref: bool = True
    include_business: bool = True
    metier_codes: list[str] | None = None


class SpecCopyFromVersionRequest(BaseModel):
    source_version_code: str
    spec_type: str  # tech, func, ref, business
    metier_code: str | None = None


# ── Tech Spec ──

class FieldSpecCreate(BaseModel):
    field_name: str
    field_label: str | None = None
    position: int
    length: int | None = None
    data_type: str = "string"
    date_format: str | None = None
    decimal_separator: str = "."
    is_nullable: bool = True
    is_unique: bool = False
    is_part_of_key: bool = False
    max_length: int | None = None
    min_value: str | None = None
    max_value: str | None = None
    regex_pattern: str | None = None
    referentiel_code: str | None = None
    default_value: str | None = None
    description: str | None = None


class FieldSpecRead(FieldSpecCreate):
    id: int
    tech_spec_id: int
    model_config = {"from_attributes": True}


class TechSpecCreate(BaseModel):
    version_id: int
    table_name: str
    file_format: str = "csv"
    separator: str = ";"
    encoding: str = "utf-8"
    has_header: bool = True
    skip_rows: int = 0
    file_name_pattern: str | None = None
    description: str | None = None
    fields: list[FieldSpecCreate] = []


class TechSpecRead(BaseModel):
    id: int
    version_id: int
    table_name: str
    file_format: str
    separator: str | None
    encoding: str | None
    has_header: bool
    skip_rows: int
    file_name_pattern: str | None
    description: str | None
    fields: list[FieldSpecRead] = []
    model_config = {"from_attributes": True}


# ── Functional Rule ──

class FuncRuleCreate(BaseModel):
    version_id: int
    table_name: str
    rule_code: str
    rule_name: str
    description: str | None = None
    condition_expr: dict | None = None
    validation_expr: dict
    severity: str = "blocking"
    error_message: str | None = None
    is_active: bool = True


class FuncRuleRead(BaseModel):
    id: int
    version_id: int
    table_name: str
    rule_code: str
    rule_name: str
    description: str | None
    condition_expr: dict | None
    validation_expr: dict
    severity: str
    error_message: str | None
    is_active: bool
    model_config = {"from_attributes": True}


# ── Reference Values ──

class RefValueCreate(BaseModel):
    version_id: int
    referentiel_code: str
    value: str
    label: str | None = None
    is_active: bool = True


class RefValueBulkCreate(BaseModel):
    version_id: int
    referentiel_code: str
    values: list[dict]  # [{"value": "X", "label": "Label X"}, ...]


class RefValueRead(BaseModel):
    id: int
    version_id: int
    referentiel_code: str
    value: str
    label: str | None
    is_active: bool
    model_config = {"from_attributes": True}


# ── Business Perimeter ──

class ExportSpecCreate(BaseModel):
    table_name: str
    export_format: str = "csv"
    file_name_template: str | None = None
    separator: str = ";"
    encoding: str = "utf-8"
    include_header: bool = True
    field_mappings: list[dict] = []
    description: str | None = None


class ExportSpecRead(ExportSpecCreate):
    id: int
    perimeter_id: int
    model_config = {"from_attributes": True}


class BusinessPerimeterCreate(BaseModel):
    version_id: int
    code_metier: str
    label: str
    description: str | None = None
    filter_rules: list[dict] | None = None
    etablissement_filter: list[str] | None = None
    cascade_filters: bool = True
    is_active: bool = True
    export_specs: list[ExportSpecCreate] = []


class BusinessPerimeterRead(BaseModel):
    id: int
    version_id: int
    code_metier: str
    label: str
    description: str | None
    filter_rules: list | None
    etablissement_filter: list | None
    cascade_filters: bool
    is_active: bool
    export_specs: list[ExportSpecRead] = []
    model_config = {"from_attributes": True}
