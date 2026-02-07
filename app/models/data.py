"""Modèles pour le stockage des données chargées (contrats, tiers, titres, liens).

Chaque table utilise une colonne JSONB `data` pour stocker les champs du fichier.
Cela permet de s'adapter aux différentes versions de spécifications sans migration.
Les index GIN sur JSONB permettent des requêtes performantes.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, JSON,
    ForeignKey, Index, text,
)

from app.database import Base


class RowStatus(str, enum.Enum):
    VALID = "valid"
    TECH_REJECTED = "tech_rejected"
    FUNC_REJECTED = "func_rejected"
    WARNING = "warning"


class DataRow(Base):
    """Ligne de données chargée depuis un flux.

    Stocke toutes les tables (contrat, tiers, titre, lien) dans une seule table
    partitionnée logiquement par table_name. Pour de très gros volumes en production,
    on peut partitionner physiquement par (table_name, flux_id).
    """
    __tablename__ = "data_row"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flux_id = Column(Integer, ForeignKey("flux.id"), nullable=False)
    table_name = Column(String(50), nullable=False)
    row_number = Column(Integer, nullable=False)  # Numéro de ligne dans le fichier
    data = Column(JSON, nullable=False)  # Données du fichier (clé = nom du champ)
    business_key = Column(String(500))  # Clé métier calculée pour détecter les doublons
    status = Column(Enum(RowStatus), nullable=False, default=RowStatus.VALID)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_data_row_flux_table", "flux_id", "table_name"),
        Index("ix_data_row_status", "flux_id", "status"),
        Index("ix_data_row_business_key", "flux_id", "table_name", "business_key"),
    )


class Rejection(Base):
    """Détail d'un rejet (technique ou fonctionnel) sur une ligne de données."""
    __tablename__ = "rejection"

    id = Column(Integer, primary_key=True, autoincrement=True)
    data_row_id = Column(Integer, ForeignKey("data_row.id"), nullable=False)
    flux_id = Column(Integer, ForeignKey("flux.id"), nullable=False)
    rejection_type = Column(String(20), nullable=False)  # "technical" ou "functional"
    rule_code = Column(String(100))  # Code de la règle ayant déclenché le rejet
    field_name = Column(String(100))  # Champ concerné
    field_value = Column(String(1000))  # Valeur du champ
    expected = Column(String(1000))  # Valeur attendue / description
    message = Column(String(2000), nullable=False)
    severity = Column(String(20), nullable=False, default="blocking")  # blocking / warning
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_rejection_flux", "flux_id"),
        Index("ix_rejection_type", "flux_id", "rejection_type"),
        Index("ix_rejection_data_row", "data_row_id"),
    )
