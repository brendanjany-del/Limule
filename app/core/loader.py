"""Moteur de chargement de fichiers (CSV, positions fixes).

Utilise Polars pour le parsing haute performance de fichiers volumineux
(plusieurs millions de lignes). Le chargement en BDD se fait par batchs.
"""

import logging
from datetime import datetime
from pathlib import Path

import polars as pl
from sqlalchemy.orm import Session

from app.models.specification import TechSpec, FieldSpec, FileFormat
from app.models.processing import Flux, FluxStatus, ProcessingStep, StepType, StepStatus
from app.models.data import DataRow, RowStatus
from app.config import settings

logger = logging.getLogger(__name__)


class FileLoader:
    """Charge un fichier en BDD selon les spécifications techniques."""

    def __init__(self, db: Session):
        self.db = db
        self.batch_size = settings.BATCH_SIZE

    def load_flux(self, flux: Flux, tech_spec: TechSpec) -> Flux:
        """Charge un flux complet en BDD.

        1. Parse le fichier selon le format (CSV ou positions fixes)
        2. Insère les données par batch dans data_row
        3. Met à jour les compteurs du flux
        """
        step = self._start_step(flux, StepType.LOADING)

        try:
            flux.status = FluxStatus.LOADING
            self.db.commit()

            file_path = Path(flux.file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"Fichier introuvable : {file_path}")

            # Parse le fichier avec Polars
            df = self._parse_file(file_path, tech_spec)
            total_lines = len(df)
            flux.total_lines = total_lines

            logger.info(f"Fichier {flux.file_name} parsé : {total_lines} lignes")

            # Prépare le mapping des noms de colonnes
            field_specs = sorted(tech_spec.fields, key=lambda f: f.position)
            field_names = [f.field_name for f in field_specs]

            # Renomme les colonnes du DataFrame
            if len(df.columns) >= len(field_names):
                rename_map = {df.columns[i]: field_names[i] for i in range(len(field_names))}
                df = df.rename(rename_map)
                # Ne garder que les colonnes spécifiées
                df = df.select(field_names)
            else:
                raise ValueError(
                    f"Le fichier a {len(df.columns)} colonnes mais la spec en attend {len(field_names)}"
                )

            # Calcule la clé métier si définie
            key_fields = [f.field_name for f in field_specs if f.is_part_of_key]

            # Charge par batchs
            loaded = 0
            for batch_start in range(0, total_lines, self.batch_size):
                batch_end = min(batch_start + self.batch_size, total_lines)
                batch_df = df.slice(batch_start, batch_end - batch_start)

                rows = []
                for row_idx in range(len(batch_df)):
                    row_data = {}
                    for col in batch_df.columns:
                        val = batch_df[col][row_idx]
                        # Convertit les valeurs Polars en types Python natifs
                        if val is None:
                            row_data[col] = None
                        else:
                            row_data[col] = str(val)

                    # Clé métier
                    bk = None
                    if key_fields:
                        bk = "|".join(str(row_data.get(k, "")) for k in key_fields)

                    rows.append(DataRow(
                        flux_id=flux.id,
                        table_name=flux.table_name,
                        row_number=batch_start + row_idx + 1,
                        data=row_data,
                        business_key=bk,
                        status=RowStatus.VALID,
                    ))

                self.db.bulk_save_objects(rows)
                self.db.flush()
                loaded += len(rows)
                logger.info(f"  Batch {batch_start}-{batch_end} chargé ({loaded}/{total_lines})")

            flux.loaded_lines = loaded
            flux.valid_lines = loaded
            flux.status = FluxStatus.LOADED
            flux.processed_at = datetime.utcnow()

            self._complete_step(step, StepStatus.SUCCESS, loaded, loaded, 0)
            self.db.commit()

            logger.info(f"Flux {flux.file_name} chargé avec succès : {loaded} lignes")
            return flux

        except Exception as e:
            logger.error(f"Erreur chargement flux {flux.file_name}: {e}")
            flux.status = FluxStatus.ERROR
            flux.error_message = str(e)
            self._complete_step(step, StepStatus.ERROR, 0, 0, 0, str(e))
            self.db.commit()
            raise

    def _parse_file(self, file_path: Path, tech_spec: TechSpec) -> pl.DataFrame:
        """Parse un fichier selon son format."""
        if tech_spec.file_format == FileFormat.CSV:
            return self._parse_csv(file_path, tech_spec)
        elif tech_spec.file_format == FileFormat.FIXED_WIDTH:
            return self._parse_fixed_width(file_path, tech_spec)
        else:
            raise ValueError(f"Format non supporté : {tech_spec.file_format}")

    def _parse_csv(self, file_path: Path, tech_spec: TechSpec) -> pl.DataFrame:
        """Parse un fichier CSV avec Polars."""
        return pl.read_csv(
            file_path,
            separator=tech_spec.separator or ";",
            encoding=tech_spec.encoding or "utf-8",
            has_header=tech_spec.has_header,
            skip_rows=tech_spec.skip_rows or 0,
            infer_schema_length=0,  # Tout en string pour contrôle technique
            null_values=["", "NULL", "null", "NA", "N/A"],
            truncate_ragged_lines=True,
        )

    def _parse_fixed_width(self, file_path: Path, tech_spec: TechSpec) -> pl.DataFrame:
        """Parse un fichier à positions fixes."""
        field_specs = sorted(tech_spec.fields, key=lambda f: f.position)
        encoding = tech_spec.encoding or "utf-8"

        rows = []
        with open(file_path, "r", encoding=encoding) as f:
            for line_no, line in enumerate(f):
                if line_no < (tech_spec.skip_rows or 0):
                    continue
                if tech_spec.has_header and line_no == (tech_spec.skip_rows or 0):
                    continue  # Skip header line

                row = {}
                for field in field_specs:
                    start = field.position - 1  # Position 1-indexed
                    end = start + (field.length or 0)
                    value = line[start:end].strip() if end <= len(line) else ""
                    row[field.field_name] = value if value else None

                rows.append(row)

        if not rows:
            return pl.DataFrame({f.field_name: [] for f in field_specs})

        return pl.DataFrame(rows)

    def _start_step(self, flux: Flux, step_type: StepType) -> ProcessingStep:
        step = ProcessingStep(
            flux_id=flux.id,
            step_type=step_type,
            status=StepStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        self.db.add(step)
        self.db.flush()
        return step

    def _complete_step(self, step: ProcessingStep, status: StepStatus,
                       processed: int, ok: int, rejected: int, error: str = None):
        step.status = status
        step.completed_at = datetime.utcnow()
        step.records_processed = processed
        step.records_ok = ok
        step.records_rejected = rejected
        step.error_message = error
