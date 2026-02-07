"""Modèles pour le suivi des traitements (établissements, arrêtés, flux, pipeline)."""

import enum
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date, Enum, JSON,
    ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class FluxStatus(str, enum.Enum):
    RECEIVED = "received"
    LOADING = "loading"
    LOADED = "loaded"
    TECH_VALIDATING = "tech_validating"
    TECH_VALIDATED = "tech_validated"
    FUNC_VALIDATING = "func_validating"
    FUNC_VALIDATED = "func_validated"
    EXPORTING = "exporting"
    EXPORTED = "exported"
    ERROR = "error"


class StepType(str, enum.Enum):
    RECEPTION = "reception"
    LOADING = "loading"
    TECH_VALIDATION = "tech_validation"
    FUNC_VALIDATION = "func_validation"
    EXPORT = "export"


class StepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class ExportJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


# ──────────────────────────────────────────────
# Établissement
# ──────────────────────────────────────────────

class Etablissement(Base):
    """Établissement bancaire."""
    __tablename__ = "etablissement"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(300), nullable=False)
    reseau_code = Column(String(50), index=True)  # Réseau d'établissements
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    arretes = relationship("Arrete", back_populates="etablissement")


# ──────────────────────────────────────────────
# Arrêté
# ──────────────────────────────────────────────

class Arrete(Base):
    """Arrêté mensuel pour un établissement."""
    __tablename__ = "arrete"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date_arrete = Column(Date, nullable=False)
    etablissement_id = Column(Integer, ForeignKey("etablissement.id"), nullable=False)
    version_id = Column(Integer, ForeignKey("spec_version.id"), nullable=False)
    status = Column(String(50), default="en_cours")  # en_cours, termine, erreur
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    etablissement = relationship("Etablissement", back_populates="arretes")
    version = relationship("SpecVersion", back_populates="arretes")
    flux = relationship("Flux", back_populates="arrete", cascade="all, delete-orphan")
    export_jobs = relationship("ExportJob", back_populates="arrete", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("date_arrete", "etablissement_id", name="uq_arrete_date_etab"),
        Index("ix_arrete_date", "date_arrete"),
    )


# ──────────────────────────────────────────────
# Flux (fichier reçu)
# ──────────────────────────────────────────────

class Flux(Base):
    """Fichier de données reçu pour un arrêté."""
    __tablename__ = "flux"

    id = Column(Integer, primary_key=True, autoincrement=True)
    arrete_id = Column(Integer, ForeignKey("arrete.id"), nullable=False)
    table_name = Column(String(50), nullable=False)  # contrat, tiers, titre, lien
    file_name = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_size = Column(Integer)  # en octets
    status = Column(Enum(FluxStatus), nullable=False, default=FluxStatus.RECEIVED)
    total_lines = Column(Integer, default=0)
    loaded_lines = Column(Integer, default=0)
    valid_lines = Column(Integer, default=0)
    tech_rejected_lines = Column(Integer, default=0)
    func_rejected_lines = Column(Integer, default=0)
    warning_lines = Column(Integer, default=0)
    error_message = Column(Text)
    received_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)

    arrete = relationship("Arrete", back_populates="flux")
    steps = relationship("ProcessingStep", back_populates="flux", cascade="all, delete-orphan",
                         order_by="ProcessingStep.started_at")

    __table_args__ = (
        Index("ix_flux_arrete_table", "arrete_id", "table_name"),
    )


# ──────────────────────────────────────────────
# Étapes de traitement (suivi pipeline)
# ──────────────────────────────────────────────

class ProcessingStep(Base):
    """Étape de traitement d'un flux (réception, chargement, validation tech/fonc, export)."""
    __tablename__ = "processing_step"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flux_id = Column(Integer, ForeignKey("flux.id"), nullable=False)
    step_type = Column(Enum(StepType), nullable=False)
    status = Column(Enum(StepStatus), nullable=False, default=StepStatus.PENDING)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    records_processed = Column(Integer, default=0)
    records_ok = Column(Integer, default=0)
    records_rejected = Column(Integer, default=0)
    records_warning = Column(Integer, default=0)
    error_message = Column(Text)
    details = Column(JSON)  # Détails supplémentaires

    flux = relationship("Flux", back_populates="steps")

    __table_args__ = (
        Index("ix_processing_step_flux", "flux_id", "step_type"),
    )


# ──────────────────────────────────────────────
# Export jobs (suivi des exports métier)
# ──────────────────────────────────────────────

class ExportJob(Base):
    """Job d'export pour un arrêté et un périmètre métier."""
    __tablename__ = "export_job"

    id = Column(Integer, primary_key=True, autoincrement=True)
    arrete_id = Column(Integer, ForeignKey("arrete.id"), nullable=False)
    perimeter_id = Column(Integer, ForeignKey("business_perimeter.id"), nullable=False)
    status = Column(Enum(ExportJobStatus), nullable=False, default=ExportJobStatus.PENDING)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    output_files = Column(JSON)  # Liste des fichiers générés
    total_records = Column(Integer, default=0)
    error_message = Column(Text)

    arrete = relationship("Arrete", back_populates="export_jobs")
    perimeter = relationship("BusinessPerimeter")

    __table_args__ = (
        UniqueConstraint("arrete_id", "perimeter_id", name="uq_export_job_arrete_perimeter"),
    )
