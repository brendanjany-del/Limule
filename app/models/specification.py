"""Modèles pour les spécifications versionnées (techniques, fonctionnelles, métier)."""

import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Enum, JSON,
    ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class TableName(str, enum.Enum):
    CONTRAT = "contrat"
    TIERS = "tiers"
    TITRE = "titre"
    LIEN = "lien"


class FileFormat(str, enum.Enum):
    CSV = "csv"
    FIXED_WIDTH = "fixed_width"


class DataType(str, enum.Enum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    BOOLEAN = "boolean"


class RuleSeverity(str, enum.Enum):
    BLOCKING = "blocking"
    WARNING = "warning"


class ExportFormat(str, enum.Enum):
    CSV = "csv"
    FIXED_WIDTH = "fixed_width"
    EXCEL = "excel"
    XML = "xml"


# ──────────────────────────────────────────────
# Version de spécification
# ──────────────────────────────────────────────

class SpecVersion(Base):
    """Version regroupant un jeu complet de spécifications."""
    __tablename__ = "spec_version"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    label = Column(String(200), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100))

    # Relations
    tech_specs = relationship("TechSpec", back_populates="version", cascade="all, delete-orphan")
    func_rules = relationship("FuncRule", back_populates="version", cascade="all, delete-orphan")
    ref_values = relationship("RefValue", back_populates="version", cascade="all, delete-orphan")
    business_perimeters = relationship("BusinessPerimeter", back_populates="version", cascade="all, delete-orphan")
    arretes = relationship("Arrete", back_populates="version")


# ──────────────────────────────────────────────
# Spécifications techniques (format fichier)
# ──────────────────────────────────────────────

class TechSpec(Base):
    """Spécification technique d'un fichier d'entrée (format, séparateur, etc.)."""
    __tablename__ = "tech_spec"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(Integer, ForeignKey("spec_version.id"), nullable=False)
    table_name = Column(Enum(TableName), nullable=False)
    file_format = Column(Enum(FileFormat), nullable=False, default=FileFormat.CSV)
    separator = Column(String(5), default=";")
    encoding = Column(String(30), default="utf-8")
    has_header = Column(Boolean, default=True)
    skip_rows = Column(Integer, default=0)
    file_name_pattern = Column(String(500))  # regex pour matcher le nom de fichier
    description = Column(Text)

    version = relationship("SpecVersion", back_populates="tech_specs")
    fields = relationship("FieldSpec", back_populates="tech_spec", cascade="all, delete-orphan",
                          order_by="FieldSpec.position")

    __table_args__ = (
        UniqueConstraint("version_id", "table_name", name="uq_tech_spec_version_table"),
    )


class FieldSpec(Base):
    """Spécification d'un champ dans un fichier."""
    __tablename__ = "field_spec"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tech_spec_id = Column(Integer, ForeignKey("tech_spec.id"), nullable=False)
    field_name = Column(String(100), nullable=False)
    field_label = Column(String(300))
    position = Column(Integer, nullable=False)  # ordre du champ (ou position pour fixed-width)
    length = Column(Integer)  # longueur (fixed-width uniquement)
    data_type = Column(Enum(DataType), nullable=False, default=DataType.STRING)
    date_format = Column(String(50))  # ex: "%Y-%m-%d", "%d/%m/%Y"
    decimal_separator = Column(String(1), default=".")
    is_nullable = Column(Boolean, default=True)
    is_unique = Column(Boolean, default=False)
    is_part_of_key = Column(Boolean, default=False)  # fait partie de la clé métier
    max_length = Column(Integer)
    min_value = Column(String(50))
    max_value = Column(String(50))
    regex_pattern = Column(String(500))
    referentiel_code = Column(String(100))  # lien vers un référentiel de valeurs autorisées
    default_value = Column(String(500))
    description = Column(Text)

    tech_spec = relationship("TechSpec", back_populates="fields")

    __table_args__ = (
        UniqueConstraint("tech_spec_id", "field_name", name="uq_field_spec_name"),
        Index("ix_field_spec_tech_position", "tech_spec_id", "position"),
    )


# ──────────────────────────────────────────────
# Règles fonctionnelles (contrôles métier)
# ──────────────────────────────────────────────

class FuncRule(Base):
    """Règle de contrôle fonctionnel/métier.

    condition_expr : condition d'application (JSON)
        ex: {"field": "code_produit", "operator": "in", "value": ["PRET_IMMO", "PRET_CONSO"]}
    validation_expr : validation à effectuer (JSON)
        ex: {"field": "taux_dar", "operator": "is_not_null"}
    Les expressions supportent : is_not_null, is_null, in, not_in, eq, neq, gt, gte, lt, lte, regex, between
    Les conditions peuvent être composées avec "and" / "or".
    """
    __tablename__ = "func_rule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(Integer, ForeignKey("spec_version.id"), nullable=False)
    table_name = Column(Enum(TableName), nullable=False)
    rule_code = Column(String(100), nullable=False)
    rule_name = Column(String(300), nullable=False)
    description = Column(Text)
    condition_expr = Column(JSON)  # Quand appliquer la règle (null = toujours)
    validation_expr = Column(JSON, nullable=False)  # Ce qu'on vérifie
    severity = Column(Enum(RuleSeverity), nullable=False, default=RuleSeverity.BLOCKING)
    error_message = Column(String(1000))
    is_active = Column(Boolean, default=True)

    version = relationship("SpecVersion", back_populates="func_rules")

    __table_args__ = (
        UniqueConstraint("version_id", "rule_code", name="uq_func_rule_version_code"),
        Index("ix_func_rule_table", "version_id", "table_name"),
    )


# ──────────────────────────────────────────────
# Référentiels de valeurs autorisées
# ──────────────────────────────────────────────

class RefValue(Base):
    """Valeur autorisée dans un référentiel."""
    __tablename__ = "ref_value"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(Integer, ForeignKey("spec_version.id"), nullable=False)
    referentiel_code = Column(String(100), nullable=False)
    value = Column(String(500), nullable=False)
    label = Column(String(500))
    is_active = Column(Boolean, default=True)

    version = relationship("SpecVersion", back_populates="ref_values")

    __table_args__ = (
        UniqueConstraint("version_id", "referentiel_code", "value", name="uq_ref_value"),
        Index("ix_ref_value_lookup", "version_id", "referentiel_code"),
    )


# ──────────────────────────────────────────────
# Périmètres métier et exports
# ──────────────────────────────────────────────

class BusinessPerimeter(Base):
    """Périmètre métier (ex: Risques, Comptabilité, etc.)

    filter_rules : filtres à appliquer pour le peuplement (JSON)
        ex: [
            {"table": "contrat", "field": "code_produit", "operator": "not_in", "value": ["PEL"]},
            {"table": "tiers", "field": "type_client", "operator": "neq", "value": "PARTICULIER"},
        ]
    etablissement_filter : liste de codes établissements ou réseaux concernés (JSON)
        ex: ["ETB001", "ETB002"] ou null pour tous
    """
    __tablename__ = "business_perimeter"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(Integer, ForeignKey("spec_version.id"), nullable=False)
    code_metier = Column(String(100), nullable=False)
    label = Column(String(300), nullable=False)
    description = Column(Text)
    filter_rules = Column(JSON)  # Règles de filtrage pour le peuplement
    etablissement_filter = Column(JSON)  # Codes établissement concernés
    cascade_filters = Column(Boolean, default=True)  # Les filtres rayonnent sur les tables liées
    is_active = Column(Boolean, default=True)

    version = relationship("SpecVersion", back_populates="business_perimeters")
    export_specs = relationship("ExportSpec", back_populates="perimeter", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("version_id", "code_metier", name="uq_business_perimeter_code"),
    )


class ExportSpec(Base):
    """Spécification d'export pour un périmètre métier.

    field_mappings : mapping des champs source -> nom export (JSON)
        ex: [
            {"source_table": "contrat", "source_field": "identifiant", "target_name": "ID_CONTRAT", "position": 1},
            ...
        ]
    """
    __tablename__ = "export_spec"

    id = Column(Integer, primary_key=True, autoincrement=True)
    perimeter_id = Column(Integer, ForeignKey("business_perimeter.id"), nullable=False)
    table_name = Column(Enum(TableName), nullable=False)
    export_format = Column(Enum(ExportFormat), nullable=False, default=ExportFormat.CSV)
    file_name_template = Column(String(500))  # ex: "{code_metier}_{table}_{date_arrete}.csv"
    separator = Column(String(5), default=";")
    encoding = Column(String(30), default="utf-8")
    include_header = Column(Boolean, default=True)
    field_mappings = Column(JSON, nullable=False)  # Liste de mappings source -> cible
    description = Column(Text)

    perimeter = relationship("BusinessPerimeter", back_populates="export_specs")

    __table_args__ = (
        UniqueConstraint("perimeter_id", "table_name", name="uq_export_spec_perimeter_table"),
    )
