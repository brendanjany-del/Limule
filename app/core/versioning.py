"""Gestion du versioning des spécifications.

Permet de :
- Créer une nouvelle version
- Copier toutes les spécifications d'une version à une autre
- Copier sélectivement par type de spec et par métier
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.specification import (
    SpecVersion, TechSpec, FieldSpec, FuncRule, RefValue,
    BusinessPerimeter, ExportSpec,
)

logger = logging.getLogger(__name__)


class VersionManager:
    """Gère les versions de spécifications."""

    def __init__(self, db: Session):
        self.db = db

    def create_version(self, code: str, label: str, description: str = None,
                       created_by: str = None) -> SpecVersion:
        """Crée une nouvelle version vide."""
        version = SpecVersion(
            code=code,
            label=label,
            description=description,
            created_by=created_by,
            is_active=True,
        )
        self.db.add(version)
        self.db.commit()
        logger.info(f"Version '{code}' créée")
        return version

    def copy_version(self, source_code: str, target_code: str, target_label: str,
                     include_tech: bool = True, include_func: bool = True,
                     include_ref: bool = True, include_business: bool = True,
                     metier_codes: list[str] = None,
                     description: str = None, created_by: str = None) -> SpecVersion:
        """Copie les spécifications d'une version source vers une nouvelle version cible.

        On peut choisir quels types de spécifications copier et filtrer par métier.
        """
        source = self.db.query(SpecVersion).filter(SpecVersion.code == source_code).first()
        if not source:
            raise ValueError(f"Version source '{source_code}' introuvable")

        # Créer la version cible
        target = self.create_version(target_code, target_label, description, created_by)

        if include_tech:
            self._copy_tech_specs(source.id, target.id)

        if include_func:
            self._copy_func_rules(source.id, target.id)

        if include_ref:
            self._copy_ref_values(source.id, target.id)

        if include_business:
            self._copy_business_perimeters(source.id, target.id, metier_codes)

        self.db.commit()
        logger.info(
            f"Version '{source_code}' copiée vers '{target_code}' "
            f"(tech={include_tech}, func={include_func}, ref={include_ref}, business={include_business})"
        )
        return target

    def copy_spec_from_version(self, target_version_code: str, source_version_code: str,
                               spec_type: str, metier_code: str = None):
        """Copie un type de spécification spécifique depuis une version choisie.

        Permet de mixer les specs de différentes versions :
        ex: prendre les specs techniques de V1 et les règles fonctionnelles de V2.
        """
        source = self.db.query(SpecVersion).filter(SpecVersion.code == source_version_code).first()
        target = self.db.query(SpecVersion).filter(SpecVersion.code == target_version_code).first()

        if not source or not target:
            raise ValueError("Version source ou cible introuvable")

        if spec_type == "tech":
            self._copy_tech_specs(source.id, target.id)
        elif spec_type == "func":
            self._copy_func_rules(source.id, target.id)
        elif spec_type == "ref":
            self._copy_ref_values(source.id, target.id)
        elif spec_type == "business":
            codes = [metier_code] if metier_code else None
            self._copy_business_perimeters(source.id, target.id, codes)
        else:
            raise ValueError(f"Type de spec inconnu: {spec_type}")

        self.db.commit()

    def _copy_tech_specs(self, source_id: int, target_id: int):
        """Copie les spécifications techniques et leurs champs."""
        specs = self.db.query(TechSpec).filter(TechSpec.version_id == source_id).all()

        for spec in specs:
            new_spec = TechSpec(
                version_id=target_id,
                table_name=spec.table_name,
                file_format=spec.file_format,
                separator=spec.separator,
                encoding=spec.encoding,
                has_header=spec.has_header,
                skip_rows=spec.skip_rows,
                file_name_pattern=spec.file_name_pattern,
                description=spec.description,
            )
            self.db.add(new_spec)
            self.db.flush()

            # Copier les champs
            fields = self.db.query(FieldSpec).filter(FieldSpec.tech_spec_id == spec.id).all()
            for field in fields:
                new_field = FieldSpec(
                    tech_spec_id=new_spec.id,
                    field_name=field.field_name,
                    field_label=field.field_label,
                    position=field.position,
                    length=field.length,
                    data_type=field.data_type,
                    date_format=field.date_format,
                    decimal_separator=field.decimal_separator,
                    is_nullable=field.is_nullable,
                    is_unique=field.is_unique,
                    is_part_of_key=field.is_part_of_key,
                    max_length=field.max_length,
                    min_value=field.min_value,
                    max_value=field.max_value,
                    regex_pattern=field.regex_pattern,
                    referentiel_code=field.referentiel_code,
                    default_value=field.default_value,
                    description=field.description,
                )
                self.db.add(new_field)

    def _copy_func_rules(self, source_id: int, target_id: int):
        """Copie les règles fonctionnelles."""
        rules = self.db.query(FuncRule).filter(FuncRule.version_id == source_id).all()

        for rule in rules:
            new_rule = FuncRule(
                version_id=target_id,
                table_name=rule.table_name,
                rule_code=rule.rule_code,
                rule_name=rule.rule_name,
                description=rule.description,
                condition_expr=rule.condition_expr,
                validation_expr=rule.validation_expr,
                severity=rule.severity,
                error_message=rule.error_message,
                is_active=rule.is_active,
            )
            self.db.add(new_rule)

    def _copy_ref_values(self, source_id: int, target_id: int):
        """Copie les valeurs de référentiel."""
        refs = self.db.query(RefValue).filter(RefValue.version_id == source_id).all()

        for ref in refs:
            new_ref = RefValue(
                version_id=target_id,
                referentiel_code=ref.referentiel_code,
                value=ref.value,
                label=ref.label,
                is_active=ref.is_active,
            )
            self.db.add(new_ref)

    def _copy_business_perimeters(self, source_id: int, target_id: int,
                                  metier_codes: list[str] = None):
        """Copie les périmètres métier et leurs specs d'export."""
        query = self.db.query(BusinessPerimeter).filter(
            BusinessPerimeter.version_id == source_id
        )
        if metier_codes:
            query = query.filter(BusinessPerimeter.code_metier.in_(metier_codes))

        perimeters = query.all()

        for perim in perimeters:
            new_perim = BusinessPerimeter(
                version_id=target_id,
                code_metier=perim.code_metier,
                label=perim.label,
                description=perim.description,
                filter_rules=perim.filter_rules,
                etablissement_filter=perim.etablissement_filter,
                cascade_filters=perim.cascade_filters,
                is_active=perim.is_active,
            )
            self.db.add(new_perim)
            self.db.flush()

            # Copier les specs d'export
            exports = (
                self.db.query(ExportSpec)
                .filter(ExportSpec.perimeter_id == perim.id)
                .all()
            )
            for exp in exports:
                new_exp = ExportSpec(
                    perimeter_id=new_perim.id,
                    table_name=exp.table_name,
                    export_format=exp.export_format,
                    file_name_template=exp.file_name_template,
                    separator=exp.separator,
                    encoding=exp.encoding,
                    include_header=exp.include_header,
                    field_mappings=exp.field_mappings,
                    description=exp.description,
                )
                self.db.add(new_exp)
