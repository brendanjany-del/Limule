"""Moteur d'export métier.

Génère les fichiers d'export selon les périmètres métier :
- Applique les filtres de peuplement (exclusion de produits, types de clients, etc.)
- Gère le rayonnement des filtres entre tables liées
- Applique le mapping de noms de champs
- Génère les fichiers au format demandé
"""

import logging
from datetime import datetime
from pathlib import Path

import polars as pl
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.specification import (
    BusinessPerimeter, ExportSpec, ExportFormat, TableName,
)
from app.models.processing import (
    Arrete, Flux, FluxStatus, ExportJob, ExportJobStatus,
    ProcessingStep, StepType, StepStatus,
)
from app.models.data import DataRow, RowStatus
from app.config import settings

logger = logging.getLogger(__name__)


class ExportEngine:
    """Génère les exports métier pour un arrêté."""

    def __init__(self, db: Session):
        self.db = db

    def export_perimeter(self, arrete: Arrete, perimeter: BusinessPerimeter) -> ExportJob:
        """Exporte les données d'un arrêté pour un périmètre métier."""
        # Créer ou récupérer le job d'export
        job = (
            self.db.query(ExportJob)
            .filter(ExportJob.arrete_id == arrete.id, ExportJob.perimeter_id == perimeter.id)
            .first()
        )
        if not job:
            job = ExportJob(
                arrete_id=arrete.id,
                perimeter_id=perimeter.id,
                status=ExportJobStatus.PENDING,
            )
            self.db.add(job)
            self.db.flush()

        try:
            job.status = ExportJobStatus.RUNNING
            job.started_at = datetime.utcnow()
            self.db.commit()

            # Récupérer les flux validés de l'arrêté
            flux_list = (
                self.db.query(Flux)
                .filter(
                    Flux.arrete_id == arrete.id,
                    Flux.status.in_([FluxStatus.FUNC_VALIDATED, FluxStatus.EXPORTED]),
                )
                .all()
            )

            flux_by_table = {f.table_name: f for f in flux_list}

            # Appliquer les filtres de peuplement pour identifier les lignes exclues
            excluded_keys = self._compute_excluded_keys(flux_by_table, perimeter)

            # Générer les fichiers d'export
            output_files = []
            total_records = 0

            for export_spec in perimeter.export_specs:
                result = self._generate_export_file(
                    arrete, flux_by_table, export_spec, excluded_keys, perimeter
                )
                if result:
                    output_files.append(result["file_path"])
                    total_records += result["record_count"]

            job.status = ExportJobStatus.SUCCESS
            job.completed_at = datetime.utcnow()
            job.output_files = output_files
            job.total_records = total_records
            self.db.commit()

            logger.info(
                f"Export {perimeter.code_metier} terminé pour arrêté {arrete.date_arrete}: "
                f"{total_records} lignes, {len(output_files)} fichiers"
            )
            return job

        except Exception as e:
            logger.error(f"Erreur export {perimeter.code_metier}: {e}")
            job.status = ExportJobStatus.ERROR
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            self.db.commit()
            raise

    def _compute_excluded_keys(self, flux_by_table: dict, perimeter: BusinessPerimeter) -> dict:
        """Calcule les clés métier à exclure selon les filtres du périmètre.

        Retourne un dict {table_name: set(business_keys_to_exclude)}.
        Si cascade_filters est True, les exclusions rayonnent entre tables liées.
        """
        excluded = {}
        filter_rules = perimeter.filter_rules or []

        for rule in filter_rules:
            table = rule.get("table")
            field = rule.get("field")
            operator = rule.get("operator")
            value = rule.get("value")

            if table not in flux_by_table:
                continue

            flux = flux_by_table[table]

            # Construire la requête pour trouver les lignes à exclure
            query = (
                self.db.query(DataRow)
                .filter(
                    DataRow.flux_id == flux.id,
                    DataRow.status == RowStatus.VALID,
                )
            )

            rows = query.all()
            keys_to_exclude = set()

            for row in rows:
                val = row.data.get(field)
                val_str = str(val) if val is not None else None

                should_exclude = False
                if operator == "eq" and val_str == str(value):
                    should_exclude = True
                elif operator == "neq" and val_str != str(value):
                    should_exclude = True
                elif operator == "in" and val_str in [str(v) for v in value]:
                    should_exclude = True
                elif operator == "not_in" and val_str not in [str(v) for v in value]:
                    should_exclude = True

                if should_exclude and row.business_key:
                    keys_to_exclude.add(row.business_key)

            if table not in excluded:
                excluded[table] = set()
            excluded[table].update(keys_to_exclude)

        # Rayonnement : si une clé est exclue dans une table,
        # exclure aussi dans les tables liées (via clé métier partagée)
        if perimeter.cascade_filters and excluded:
            all_excluded_keys = set()
            for keys in excluded.values():
                all_excluded_keys.update(keys)

            for table_name in flux_by_table:
                if table_name not in excluded:
                    excluded[table_name] = set()
                excluded[table_name].update(all_excluded_keys)

        return excluded

    def _generate_export_file(self, arrete: Arrete, flux_by_table: dict,
                              export_spec: ExportSpec, excluded_keys: dict,
                              perimeter: BusinessPerimeter) -> dict | None:
        """Génère un fichier d'export."""
        table_name = export_spec.table_name.value

        if table_name not in flux_by_table:
            logger.warning(f"Table {table_name} non trouvée dans les flux de l'arrêté")
            return None

        flux = flux_by_table[table_name]
        excluded = excluded_keys.get(table_name, set())

        # Charger les lignes valides
        rows = (
            self.db.query(DataRow)
            .filter(
                DataRow.flux_id == flux.id,
                DataRow.status == RowStatus.VALID,
            )
            .all()
        )

        # Filtrer les lignes exclues
        valid_rows = [r for r in rows if not r.business_key or r.business_key not in excluded]

        if not valid_rows:
            return None

        # Appliquer le mapping de champs
        mappings = export_spec.field_mappings or []
        mappings_sorted = sorted(mappings, key=lambda m: m.get("position", 0))

        export_data = []
        for row in valid_rows:
            export_row = {}
            for mapping in mappings_sorted:
                source_field = mapping.get("source_field")
                target_name = mapping.get("target_name", source_field)
                value = row.data.get(source_field)
                export_row[target_name] = value
            export_data.append(export_row)

        # Créer le DataFrame Polars pour l'export
        df = pl.DataFrame(export_data)

        # Générer le nom du fichier
        file_name = (export_spec.file_name_template or "{code_metier}_{table}_{date_arrete}.csv").format(
            code_metier=perimeter.code_metier,
            table=table_name,
            date_arrete=arrete.date_arrete.strftime("%Y%m%d"),
            etablissement=arrete.etablissement.code if arrete.etablissement else "UNKNOWN",
        )

        output_path = Path(settings.DATA_OUTPUT_DIR) / file_name

        # Écrire le fichier
        if export_spec.export_format == ExportFormat.CSV:
            df.write_csv(
                output_path,
                separator=export_spec.separator or ";",
                include_header=export_spec.include_header,
            )
        elif export_spec.export_format == ExportFormat.EXCEL:
            # Polars supporte l'export Excel si xlsxwriter est installé
            df.write_excel(output_path)
        else:
            df.write_csv(output_path, separator=export_spec.separator or ";")

        logger.info(f"  Export {file_name}: {len(valid_rows)} lignes")

        return {
            "file_path": str(output_path),
            "file_name": file_name,
            "record_count": len(valid_rows),
        }
