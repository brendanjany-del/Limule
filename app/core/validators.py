"""Moteurs de validation technique et fonctionnelle.

- TechnicalValidator : contrôles de format, type, intégrité, doublons
- FunctionalValidator : contrôles métier basés sur les règles fonctionnelles
"""

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.specification import (
    TechSpec, FieldSpec, DataType, FuncRule, RuleSeverity, RefValue,
)
from app.models.processing import (
    Flux, FluxStatus, ProcessingStep, StepType, StepStatus,
)
from app.models.data import DataRow, RowStatus, Rejection
from app.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Validation technique
# ──────────────────────────────────────────────

class TechnicalValidator:
    """Contrôles techniques : format, type, longueur, nullable, unicité, doublons."""

    def __init__(self, db: Session):
        self.db = db
        self.batch_size = settings.BATCH_SIZE

    def validate_flux(self, flux: Flux, tech_spec: TechSpec) -> Flux:
        """Valide techniquement toutes les lignes d'un flux."""
        step = self._start_step(flux, StepType.TECH_VALIDATION)

        try:
            flux.status = FluxStatus.TECH_VALIDATING
            self.db.commit()

            field_specs = {f.field_name: f for f in tech_spec.fields}

            # Charger les valeurs de référentiel nécessaires
            ref_codes = {f.referentiel_code for f in tech_spec.fields if f.referentiel_code}
            ref_cache = self._load_ref_values(tech_spec.version_id, ref_codes)

            total_processed = 0
            total_ok = 0
            total_rejected = 0
            total_warning = 0

            # Traitement par batchs
            offset = 0
            while True:
                rows = (
                    self.db.query(DataRow)
                    .filter(DataRow.flux_id == flux.id, DataRow.status == RowStatus.VALID)
                    .order_by(DataRow.id)
                    .offset(offset)
                    .limit(self.batch_size)
                    .all()
                )
                if not rows:
                    break

                rejections_batch = []

                for row in rows:
                    row_rejections = self._validate_row(row, field_specs, ref_cache)

                    if row_rejections:
                        has_blocking = any(r.severity == "blocking" for r in row_rejections)
                        if has_blocking:
                            row.status = RowStatus.TECH_REJECTED
                            total_rejected += 1
                        else:
                            row.status = RowStatus.WARNING
                            total_warning += 1
                        rejections_batch.extend(row_rejections)
                    else:
                        total_ok += 1

                    total_processed += 1

                if rejections_batch:
                    self.db.bulk_save_objects(rejections_batch)

                self.db.flush()
                offset += self.batch_size
                logger.info(f"  Validation technique batch: {total_processed} lignes traitées")

            # Détection de doublons sur la clé métier
            dup_rejected = self._check_duplicates(flux)
            total_rejected += dup_rejected
            total_ok -= dup_rejected

            # Mise à jour des compteurs
            flux.tech_rejected_lines = total_rejected
            flux.warning_lines = total_warning
            flux.valid_lines = flux.loaded_lines - total_rejected
            flux.status = FluxStatus.TECH_VALIDATED

            self._complete_step(step, StepStatus.SUCCESS, total_processed, total_ok, total_rejected)
            self.db.commit()

            logger.info(
                f"Validation technique terminée pour {flux.file_name}: "
                f"{total_ok} OK, {total_rejected} rejetés, {total_warning} warnings"
            )
            return flux

        except Exception as e:
            logger.error(f"Erreur validation technique {flux.file_name}: {e}")
            flux.status = FluxStatus.ERROR
            flux.error_message = str(e)
            self._complete_step(step, StepStatus.ERROR, 0, 0, 0, str(e))
            self.db.commit()
            raise

    def _validate_row(self, row: DataRow, field_specs: dict, ref_cache: dict) -> list[Rejection]:
        """Valide une ligne de données selon les spécifications des champs."""
        rejections = []
        data = row.data or {}

        for field_name, spec in field_specs.items():
            value = data.get(field_name)
            value_str = str(value).strip() if value is not None else None
            is_empty = value is None or value_str == ""

            # Contrôle nullable
            if not spec.is_nullable and is_empty:
                rejections.append(self._make_rejection(
                    row, "technical", f"TECH_NULLABLE_{field_name}",
                    field_name, value_str, "Valeur non nulle attendue",
                    f"Le champ '{spec.field_label or field_name}' est obligatoire",
                    "blocking"
                ))
                continue

            if is_empty:
                continue

            # Contrôle de type
            type_error = self._check_type(value_str, spec)
            if type_error:
                rejections.append(self._make_rejection(
                    row, "technical", f"TECH_TYPE_{field_name}",
                    field_name, value_str, f"Type attendu: {spec.data_type.value}",
                    type_error, "blocking"
                ))
                continue

            # Contrôle de longueur max
            if spec.max_length and len(value_str) > spec.max_length:
                rejections.append(self._make_rejection(
                    row, "technical", f"TECH_MAXLEN_{field_name}",
                    field_name, value_str, f"Max {spec.max_length} caractères",
                    f"Le champ '{spec.field_label or field_name}' dépasse la longueur max ({len(value_str)} > {spec.max_length})",
                    "blocking"
                ))

            # Contrôle de pattern regex
            if spec.regex_pattern and not re.match(spec.regex_pattern, value_str):
                rejections.append(self._make_rejection(
                    row, "technical", f"TECH_PATTERN_{field_name}",
                    field_name, value_str, f"Pattern attendu: {spec.regex_pattern}",
                    f"Le champ '{spec.field_label or field_name}' ne respecte pas le format attendu",
                    "blocking"
                ))

            # Contrôle min/max
            if spec.min_value or spec.max_value:
                range_error = self._check_range(value_str, spec)
                if range_error:
                    rejections.append(self._make_rejection(
                        row, "technical", f"TECH_RANGE_{field_name}",
                        field_name, value_str,
                        f"[{spec.min_value}, {spec.max_value}]",
                        range_error, "blocking"
                    ))

            # Contrôle référentiel
            if spec.referentiel_code:
                allowed = ref_cache.get(spec.referentiel_code, set())
                if allowed and value_str not in allowed:
                    rejections.append(self._make_rejection(
                        row, "technical", f"TECH_REF_{field_name}",
                        field_name, value_str,
                        f"Référentiel: {spec.referentiel_code}",
                        f"Valeur '{value_str}' non autorisée dans le référentiel '{spec.referentiel_code}'",
                        "blocking"
                    ))

        return rejections

    def _check_type(self, value: str, spec: FieldSpec) -> Optional[str]:
        """Vérifie que la valeur correspond au type attendu."""
        if spec.data_type == DataType.INTEGER:
            try:
                int(value)
            except ValueError:
                return f"'{value}' n'est pas un entier valide pour '{spec.field_label or spec.field_name}'"

        elif spec.data_type == DataType.DECIMAL:
            try:
                sep = spec.decimal_separator or "."
                Decimal(value.replace(sep, "."))
            except InvalidOperation:
                return f"'{value}' n'est pas un décimal valide pour '{spec.field_label or spec.field_name}'"

        elif spec.data_type == DataType.DATE:
            fmt = spec.date_format or "%Y-%m-%d"
            try:
                datetime.strptime(value, fmt)
            except ValueError:
                return f"'{value}' n'est pas une date valide (format attendu: {fmt}) pour '{spec.field_label or spec.field_name}'"

        elif spec.data_type == DataType.BOOLEAN:
            if value.lower() not in ("true", "false", "0", "1", "oui", "non", "o", "n"):
                return f"'{value}' n'est pas un booléen valide pour '{spec.field_label or spec.field_name}'"

        return None

    def _check_range(self, value: str, spec: FieldSpec) -> Optional[str]:
        """Vérifie que la valeur est dans la plage autorisée."""
        try:
            if spec.data_type in (DataType.INTEGER, DataType.DECIMAL):
                num = Decimal(value.replace(spec.decimal_separator or ".", "."))
                if spec.min_value and num < Decimal(spec.min_value):
                    return f"Valeur {value} inférieure au minimum {spec.min_value}"
                if spec.max_value and num > Decimal(spec.max_value):
                    return f"Valeur {value} supérieure au maximum {spec.max_value}"
        except (InvalidOperation, ValueError):
            pass
        return None

    def _check_duplicates(self, flux: Flux) -> int:
        """Détecte les doublons sur la clé métier."""
        # Trouve les clés en double
        duplicates = (
            self.db.query(DataRow.business_key)
            .filter(
                DataRow.flux_id == flux.id,
                DataRow.status == RowStatus.VALID,
                DataRow.business_key.isnot(None),
            )
            .group_by(DataRow.business_key)
            .having(func.count() > 1)
            .all()
        )

        if not duplicates:
            return 0

        dup_keys = {d[0] for d in duplicates}
        rejected_count = 0

        for dup_key in dup_keys:
            rows = (
                self.db.query(DataRow)
                .filter(
                    DataRow.flux_id == flux.id,
                    DataRow.business_key == dup_key,
                    DataRow.status == RowStatus.VALID,
                )
                .order_by(DataRow.row_number)
                .all()
            )
            # Garde la première occurrence, rejette les suivantes
            for row in rows[1:]:
                row.status = RowStatus.TECH_REJECTED
                self.db.add(Rejection(
                    data_row_id=row.id,
                    flux_id=flux.id,
                    rejection_type="technical",
                    rule_code="TECH_DUPLICATE",
                    field_name="business_key",
                    field_value=dup_key,
                    expected="Clé unique",
                    message=f"Doublon détecté sur la clé métier '{dup_key}' (première occurrence ligne {rows[0].row_number})",
                    severity="blocking",
                ))
                rejected_count += 1

        self.db.flush()
        return rejected_count

    def _load_ref_values(self, version_id: int, ref_codes: set) -> dict:
        """Charge les valeurs de référentiel en cache."""
        if not ref_codes:
            return {}

        refs = (
            self.db.query(RefValue)
            .filter(
                RefValue.version_id == version_id,
                RefValue.referentiel_code.in_(ref_codes),
                RefValue.is_active == True,
            )
            .all()
        )

        cache = {}
        for ref in refs:
            if ref.referentiel_code not in cache:
                cache[ref.referentiel_code] = set()
            cache[ref.referentiel_code].add(ref.value)

        return cache

    def _make_rejection(self, row, rejection_type, rule_code, field_name,
                        field_value, expected, message, severity):
        return Rejection(
            data_row_id=row.id,
            flux_id=row.flux_id,
            rejection_type=rejection_type,
            rule_code=rule_code,
            field_name=field_name,
            field_value=field_value,
            expected=expected,
            message=message,
            severity=severity,
        )

    def _start_step(self, flux, step_type):
        step = ProcessingStep(
            flux_id=flux.id,
            step_type=step_type,
            status=StepStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        self.db.add(step)
        self.db.flush()
        return step

    def _complete_step(self, step, status, processed, ok, rejected, error=None):
        step.status = status
        step.completed_at = datetime.utcnow()
        step.records_processed = processed
        step.records_ok = ok
        step.records_rejected = rejected
        step.error_message = error


# ──────────────────────────────────────────────
# Validation fonctionnelle / métier
# ──────────────────────────────────────────────

class FunctionalValidator:
    """Contrôles fonctionnels basés sur les règles métier."""

    def __init__(self, db: Session):
        self.db = db
        self.batch_size = settings.BATCH_SIZE

    def validate_flux(self, flux: Flux, rules: list[FuncRule]) -> Flux:
        """Valide fonctionnellement toutes les lignes valides d'un flux."""
        step = self._start_step(flux, StepType.FUNC_VALIDATION)

        try:
            flux.status = FluxStatus.FUNC_VALIDATING
            self.db.commit()

            # Filtrer les règles actives pour cette table
            table_rules = [r for r in rules if r.table_name.value == flux.table_name and r.is_active]

            if not table_rules:
                logger.info(f"Aucune règle fonctionnelle pour {flux.table_name}")
                flux.status = FluxStatus.FUNC_VALIDATED
                self._complete_step(step, StepStatus.SUCCESS, 0, 0, 0)
                self.db.commit()
                return flux

            total_processed = 0
            total_ok = 0
            total_rejected = 0
            total_warning = 0

            offset = 0
            while True:
                rows = (
                    self.db.query(DataRow)
                    .filter(
                        DataRow.flux_id == flux.id,
                        DataRow.status.in_([RowStatus.VALID, RowStatus.WARNING]),
                    )
                    .order_by(DataRow.id)
                    .offset(offset)
                    .limit(self.batch_size)
                    .all()
                )
                if not rows:
                    break

                rejections_batch = []

                for row in rows:
                    row_rejections = self._apply_rules(row, table_rules)

                    if row_rejections:
                        has_blocking = any(r.severity == "blocking" for r in row_rejections)
                        if has_blocking:
                            row.status = RowStatus.FUNC_REJECTED
                            total_rejected += 1
                        else:
                            row.status = RowStatus.WARNING
                            total_warning += 1
                        rejections_batch.extend(row_rejections)
                    else:
                        total_ok += 1

                    total_processed += 1

                if rejections_batch:
                    self.db.bulk_save_objects(rejections_batch)

                self.db.flush()
                offset += self.batch_size

            flux.func_rejected_lines = total_rejected
            flux.warning_lines += total_warning
            flux.valid_lines = flux.loaded_lines - flux.tech_rejected_lines - total_rejected
            flux.status = FluxStatus.FUNC_VALIDATED

            self._complete_step(step, StepStatus.SUCCESS, total_processed, total_ok, total_rejected)
            self.db.commit()

            logger.info(
                f"Validation fonctionnelle terminée pour {flux.file_name}: "
                f"{total_ok} OK, {total_rejected} rejetés, {total_warning} warnings"
            )
            return flux

        except Exception as e:
            logger.error(f"Erreur validation fonctionnelle {flux.file_name}: {e}")
            flux.status = FluxStatus.ERROR
            flux.error_message = str(e)
            self._complete_step(step, StepStatus.ERROR, 0, 0, 0, str(e))
            self.db.commit()
            raise

    def _apply_rules(self, row: DataRow, rules: list[FuncRule]) -> list[Rejection]:
        """Applique toutes les règles fonctionnelles à une ligne."""
        rejections = []
        data = row.data or {}

        for rule in rules:
            # Vérifie si la condition d'application est remplie
            if rule.condition_expr:
                if not self._evaluate_expr(data, rule.condition_expr):
                    continue  # Règle non applicable

            # Vérifie la validation
            if not self._evaluate_expr(data, rule.validation_expr):
                severity = "blocking" if rule.severity == RuleSeverity.BLOCKING else "warning"
                rejections.append(Rejection(
                    data_row_id=row.id,
                    flux_id=row.flux_id,
                    rejection_type="functional",
                    rule_code=rule.rule_code,
                    field_name=self._extract_field(rule.validation_expr),
                    field_value=str(data.get(self._extract_field(rule.validation_expr), "")),
                    expected=rule.error_message or rule.rule_name,
                    message=rule.error_message or f"Règle '{rule.rule_name}' non respectée",
                    severity=severity,
                ))

        return rejections

    def _evaluate_expr(self, data: dict, expr: dict) -> bool:
        """Évalue une expression de condition/validation.

        Formats supportés :
        - Simple : {"field": "x", "operator": "eq", "value": "y"}
        - Composée : {"and": [...]} ou {"or": [...]}
        """
        if not expr:
            return True

        # Expressions composées
        if "and" in expr:
            return all(self._evaluate_expr(data, sub) for sub in expr["and"])
        if "or" in expr:
            return any(self._evaluate_expr(data, sub) for sub in expr["or"])

        field = expr.get("field")
        operator = expr.get("operator")
        expected = expr.get("value")

        if not field or not operator:
            return True

        actual = data.get(field)
        actual_str = str(actual).strip() if actual is not None else None
        is_empty = actual is None or actual_str == ""

        if operator == "is_not_null":
            return not is_empty
        elif operator == "is_null":
            return is_empty
        elif operator == "eq":
            return actual_str == str(expected)
        elif operator == "neq":
            return actual_str != str(expected)
        elif operator == "in":
            return actual_str in [str(v) for v in expected] if isinstance(expected, list) else False
        elif operator == "not_in":
            return actual_str not in [str(v) for v in expected] if isinstance(expected, list) else True
        elif operator == "gt":
            return self._compare_numeric(actual_str, expected, lambda a, b: a > b)
        elif operator == "gte":
            return self._compare_numeric(actual_str, expected, lambda a, b: a >= b)
        elif operator == "lt":
            return self._compare_numeric(actual_str, expected, lambda a, b: a < b)
        elif operator == "lte":
            return self._compare_numeric(actual_str, expected, lambda a, b: a <= b)
        elif operator == "regex":
            return bool(re.match(str(expected), actual_str)) if not is_empty else False
        elif operator == "between":
            if isinstance(expected, list) and len(expected) == 2:
                return self._compare_numeric(actual_str, expected[0], lambda a, b: a >= b) and \
                       self._compare_numeric(actual_str, expected[1], lambda a, b: a <= b)
            return False
        elif operator == "starts_with":
            return actual_str.startswith(str(expected)) if not is_empty else False
        elif operator == "contains":
            return str(expected) in actual_str if not is_empty else False

        return True

    def _compare_numeric(self, actual: str, expected, comparator) -> bool:
        try:
            return comparator(Decimal(actual), Decimal(str(expected)))
        except (InvalidOperation, ValueError, TypeError):
            return False

    def _extract_field(self, expr: dict) -> str:
        """Extrait le nom du champ principal d'une expression."""
        if "field" in expr:
            return expr["field"]
        if "and" in expr and expr["and"]:
            return self._extract_field(expr["and"][0])
        if "or" in expr and expr["or"]:
            return self._extract_field(expr["or"][0])
        return ""

    def _start_step(self, flux, step_type):
        step = ProcessingStep(
            flux_id=flux.id,
            step_type=step_type,
            status=StepStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        self.db.add(step)
        self.db.flush()
        return step

    def _complete_step(self, step, status, processed, ok, rejected, error=None):
        step.status = status
        step.completed_at = datetime.utcnow()
        step.records_processed = processed
        step.records_ok = ok
        step.records_rejected = rejected
        step.error_message = error
