"""Orchestrateur du pipeline de traitement complet.

Coordonne les étapes : réception -> chargement -> validation technique
-> validation fonctionnelle -> export métier.
"""

import logging
import os
import re
from datetime import datetime, date
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.specification import SpecVersion, TechSpec, FuncRule, BusinessPerimeter
from app.models.processing import (
    Etablissement, Arrete, Flux, FluxStatus,
    ProcessingStep, StepType, StepStatus,
)
from app.core.loader import FileLoader
from app.core.validators import TechnicalValidator, FunctionalValidator
from app.core.export_engine import ExportEngine
from app.config import settings

logger = logging.getLogger(__name__)


class Pipeline:
    """Pipeline de traitement des flux de données bancaires."""

    def __init__(self, db: Session):
        self.db = db
        self.loader = FileLoader(db)
        self.tech_validator = TechnicalValidator(db)
        self.func_validator = FunctionalValidator(db)
        self.export_engine = ExportEngine(db)

    def receive_file(
        self,
        file_path: str,
        file_name: str,
        etablissement_code: str,
        date_arrete: date,
        table_name: str,
        version_code: str,
    ) -> Flux:
        """Réceptionne un fichier et l'enregistre comme flux.

        Le nom du fichier contient les métadonnées :
        ex: V2024_01_ETB001_202401_contrat.csv
            -> version=V2024_01, etablissement=ETB001, date=202401, table=contrat
        """
        # Résoudre la version
        version = self.db.query(SpecVersion).filter(SpecVersion.code == version_code).first()
        if not version:
            raise ValueError(f"Version de spécification '{version_code}' introuvable")

        # Résoudre ou créer l'établissement
        etablissement = (
            self.db.query(Etablissement)
            .filter(Etablissement.code == etablissement_code)
            .first()
        )
        if not etablissement:
            etablissement = Etablissement(code=etablissement_code, name=etablissement_code)
            self.db.add(etablissement)
            self.db.flush()

        # Résoudre ou créer l'arrêté
        arrete = (
            self.db.query(Arrete)
            .filter(
                Arrete.date_arrete == date_arrete,
                Arrete.etablissement_id == etablissement.id,
            )
            .first()
        )
        if not arrete:
            arrete = Arrete(
                date_arrete=date_arrete,
                etablissement_id=etablissement.id,
                version_id=version.id,
                status="en_cours",
            )
            self.db.add(arrete)
            self.db.flush()

        # Créer le flux
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        flux = Flux(
            arrete_id=arrete.id,
            table_name=table_name,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            status=FluxStatus.RECEIVED,
        )
        self.db.add(flux)
        self.db.flush()  # Assigner l'id au flux

        # Étape de réception
        step = ProcessingStep(
            flux_id=flux.id,
            step_type=StepType.RECEPTION,
            status=StepStatus.SUCCESS,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        self.db.add(step)
        self.db.commit()

        logger.info(f"Flux reçu : {file_name} (établissement={etablissement_code}, arrêté={date_arrete})")
        return flux

    def process_flux(self, flux_id: int) -> Flux:
        """Exécute le pipeline complet pour un flux : chargement + validations."""
        flux = self.db.query(Flux).get(flux_id)
        if not flux:
            raise ValueError(f"Flux {flux_id} introuvable")

        arrete = flux.arrete
        version = arrete.version

        # 1. Chargement
        if flux.status == FluxStatus.RECEIVED:
            tech_spec = (
                self.db.query(TechSpec)
                .filter(
                    TechSpec.version_id == version.id,
                    TechSpec.table_name == flux.table_name,
                )
                .first()
            )
            if not tech_spec:
                raise ValueError(
                    f"Spécification technique introuvable pour version={version.code}, "
                    f"table={flux.table_name}"
                )
            self.loader.load_flux(flux, tech_spec)

        # 2. Validation technique
        if flux.status == FluxStatus.LOADED:
            tech_spec = (
                self.db.query(TechSpec)
                .filter(
                    TechSpec.version_id == version.id,
                    TechSpec.table_name == flux.table_name,
                )
                .first()
            )
            self.tech_validator.validate_flux(flux, tech_spec)

        # 3. Validation fonctionnelle
        if flux.status == FluxStatus.TECH_VALIDATED:
            rules = (
                self.db.query(FuncRule)
                .filter(FuncRule.version_id == version.id)
                .all()
            )
            self.func_validator.validate_flux(flux, rules)

        return flux

    def process_arrete(self, arrete_id: int) -> Arrete:
        """Traite tous les flux d'un arrêté."""
        arrete = self.db.query(Arrete).get(arrete_id)
        if not arrete:
            raise ValueError(f"Arrêté {arrete_id} introuvable")

        for flux in arrete.flux:
            try:
                self.process_flux(flux.id)
            except Exception as e:
                logger.error(f"Erreur traitement flux {flux.file_name}: {e}")
                continue

        # Vérifier si tous les flux sont validés
        all_validated = all(
            f.status in (FluxStatus.FUNC_VALIDATED, FluxStatus.EXPORTED)
            for f in arrete.flux
        )
        if all_validated:
            arrete.status = "valide"
        elif any(f.status == FluxStatus.ERROR for f in arrete.flux):
            arrete.status = "erreur"
        else:
            arrete.status = "en_cours"

        arrete.updated_at = datetime.utcnow()
        self.db.commit()

        return arrete

    def export_arrete(self, arrete_id: int, perimeter_code: str = None) -> list:
        """Exporte les données d'un arrêté pour un ou tous les périmètres métier."""
        arrete = self.db.query(Arrete).get(arrete_id)
        if not arrete:
            raise ValueError(f"Arrêté {arrete_id} introuvable")

        version = arrete.version
        query = self.db.query(BusinessPerimeter).filter(
            BusinessPerimeter.version_id == version.id,
            BusinessPerimeter.is_active == True,
        )
        if perimeter_code:
            query = query.filter(BusinessPerimeter.code_metier == perimeter_code)

        perimeters = query.all()
        jobs = []

        for perimeter in perimeters:
            # Vérifier si l'établissement fait partie du périmètre
            etab_filter = perimeter.etablissement_filter
            if etab_filter:
                etab_code = arrete.etablissement.code
                reseau_code = arrete.etablissement.reseau_code
                if etab_code not in etab_filter and reseau_code not in etab_filter:
                    continue

            try:
                job = self.export_engine.export_perimeter(arrete, perimeter)
                jobs.append(job)
            except Exception as e:
                logger.error(f"Erreur export périmètre {perimeter.code_metier}: {e}")
                continue

        return jobs

    def parse_file_name(self, file_name: str) -> dict | None:
        """Parse le nom d'un fichier pour extraire les métadonnées.

        Convention de nommage :
        {version}_{etablissement}_{YYYYMM}_{table}.{ext}
        ex: V2024_01_ETB001_202401_contrat.csv
        """
        pattern = r"^(.+?)_([A-Z0-9]+)_(\d{6})_(contrat|tiers|titre|lien)\.\w+$"
        match = re.match(pattern, file_name, re.IGNORECASE)
        if not match:
            return None

        return {
            "version_code": match.group(1),
            "etablissement_code": match.group(2),
            "date_arrete": date(int(match.group(3)[:4]), int(match.group(3)[4:6]), 1),
            "table_name": match.group(4).lower(),
        }
