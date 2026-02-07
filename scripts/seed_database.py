"""Script de seed pour initialiser la BDD avec des spécifications d'exemple bancaire.

Usage : python -m scripts.seed_database
Nécessite que PostgreSQL soit lancé et que les tables soient créées.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import sync_engine, SyncSessionLocal, Base
from app.models.specification import (
    SpecVersion, TechSpec, FieldSpec, FuncRule, RefValue,
    BusinessPerimeter, ExportSpec,
    TableName, FileFormat, DataType, RuleSeverity, ExportFormat,
)
from app.models.processing import Etablissement
from app.models import data as _data_models  # noqa: F401 - ensure data tables are created


def seed():
    Base.metadata.create_all(sync_engine)
    db = SyncSessionLocal()

    try:
        # ── Version ──
        version = SpecVersion(
            code="V2024_01",
            label="Version Janvier 2024",
            description="Première version des spécifications réglementaires",
            created_by="system",
        )
        db.add(version)
        db.flush()

        # ── Établissement ──
        etab = Etablissement(code="ETB001", name="Banque Nationale de Test", reseau_code="RESEAU_A")
        db.add(etab)

        # ── Spec technique CONTRAT ──
        spec_contrat = TechSpec(
            version_id=version.id, table_name=TableName.CONTRAT,
            file_format=FileFormat.CSV, separator=";", encoding="utf-8",
            has_header=True, file_name_pattern=r".*_contrat\.csv$",
        )
        db.add(spec_contrat)
        db.flush()

        contrat_fields = [
            ("identifiant_contrat", "Identifiant du contrat", DataType.STRING, False, True, None, None),
            ("code_etablissement", "Code établissement", DataType.STRING, False, False, None, "REF_ETABLISSEMENT"),
            ("code_produit", "Code produit", DataType.STRING, False, False, None, "REF_PRODUIT"),
            ("type_produit", "Type de produit", DataType.STRING, False, False, None, "REF_TYPE_PRODUIT"),
            ("date_ouverture", "Date d'ouverture", DataType.DATE, False, False, "%Y-%m-%d", None),
            ("date_echeance", "Date d'échéance", DataType.DATE, True, False, "%Y-%m-%d", None),
            ("montant_initial", "Montant initial", DataType.DECIMAL, False, False, None, None),
            ("montant_restant_du", "Montant restant dû", DataType.DECIMAL, True, False, None, None),
            ("devise", "Devise", DataType.STRING, False, False, None, "REF_DEVISE"),
            ("type_taux", "Type de taux", DataType.STRING, True, False, None, "REF_TYPE_TAUX"),
            ("taux_dar", "Taux à la DAR", DataType.DECIMAL, True, False, None, None),
            ("duree_initiale_mois", "Durée initiale (mois)", DataType.INTEGER, True, False, None, None),
            ("identifiant_tiers", "Identifiant du tiers titulaire", DataType.STRING, False, False, None, None),
            ("statut_contrat", "Statut du contrat", DataType.STRING, False, False, None, "REF_STATUT_CONTRAT"),
            ("segment_clientele", "Segment clientèle", DataType.STRING, True, False, None, None),
        ]
        for i, (name, label, dtype, nullable, is_key, dfmt, ref) in enumerate(contrat_fields, 1):
            db.add(FieldSpec(
                tech_spec_id=spec_contrat.id, field_name=name, field_label=label,
                position=i, data_type=dtype, is_nullable=nullable, is_part_of_key=is_key,
                date_format=dfmt, referentiel_code=ref,
            ))

        # ── Spec technique TIERS ──
        spec_tiers = TechSpec(
            version_id=version.id, table_name=TableName.TIERS,
            file_format=FileFormat.CSV, separator=";", encoding="utf-8",
            has_header=True, file_name_pattern=r".*_tiers\.csv$",
        )
        db.add(spec_tiers)
        db.flush()

        tiers_fields = [
            ("identifiant_tiers", "Identifiant du tiers", DataType.STRING, False, True, None, None),
            ("type_tiers", "Type de tiers", DataType.STRING, False, False, None, "REF_TYPE_TIERS"),
            ("raison_sociale", "Raison sociale", DataType.STRING, True, False, None, None),
            ("code_naf", "Code NAF", DataType.STRING, True, False, None, None),
            ("pays_residence", "Pays de résidence", DataType.STRING, False, False, None, "REF_PAYS"),
            ("segment_clientele", "Segment clientèle", DataType.STRING, True, False, None, "REF_SEGMENT"),
            ("notation_interne", "Notation interne", DataType.STRING, True, False, None, None),
            ("date_entree_relation", "Date d'entrée en relation", DataType.DATE, False, False, "%Y-%m-%d", None),
            ("est_defaut", "En défaut", DataType.BOOLEAN, False, False, None, None),
            ("date_defaut", "Date de défaut", DataType.DATE, True, False, "%Y-%m-%d", None),
        ]
        for i, (name, label, dtype, nullable, is_key, dfmt, ref) in enumerate(tiers_fields, 1):
            db.add(FieldSpec(
                tech_spec_id=spec_tiers.id, field_name=name, field_label=label,
                position=i, data_type=dtype, is_nullable=nullable, is_part_of_key=is_key,
                date_format=dfmt, referentiel_code=ref,
            ))

        # ── Spec technique TITRE ──
        spec_titre = TechSpec(
            version_id=version.id, table_name=TableName.TITRE,
            file_format=FileFormat.CSV, separator=";", encoding="utf-8",
            has_header=True, file_name_pattern=r".*_titre\.csv$",
        )
        db.add(spec_titre)
        db.flush()

        titre_fields = [
            ("identifiant_titre", "Identifiant du titre", DataType.STRING, False, True, None, None),
            ("code_isin", "Code ISIN", DataType.STRING, False, False, None, None),
            ("type_titre", "Type de titre", DataType.STRING, False, False, None, "REF_TYPE_TITRE"),
            ("emetteur", "Émetteur", DataType.STRING, False, False, None, None),
            ("valeur_nominale", "Valeur nominale", DataType.DECIMAL, False, False, None, None),
            ("valeur_marche", "Valeur de marché", DataType.DECIMAL, True, False, None, None),
            ("devise", "Devise", DataType.STRING, False, False, None, "REF_DEVISE"),
            ("date_emission", "Date d'émission", DataType.DATE, False, False, "%Y-%m-%d", None),
            ("date_maturite", "Date de maturité", DataType.DATE, True, False, "%Y-%m-%d", None),
        ]
        for i, (name, label, dtype, nullable, is_key, dfmt, ref) in enumerate(titre_fields, 1):
            db.add(FieldSpec(
                tech_spec_id=spec_titre.id, field_name=name, field_label=label,
                position=i, data_type=dtype, is_nullable=nullable, is_part_of_key=is_key,
                date_format=dfmt, referentiel_code=ref,
            ))

        # ── Spec technique LIEN ──
        spec_lien = TechSpec(
            version_id=version.id, table_name=TableName.LIEN,
            file_format=FileFormat.CSV, separator=";", encoding="utf-8",
            has_header=True, file_name_pattern=r".*_lien\.csv$",
        )
        db.add(spec_lien)
        db.flush()

        lien_fields = [
            ("identifiant_lien", "Identifiant du lien", DataType.STRING, False, True, None, None),
            ("type_lien", "Type de lien", DataType.STRING, False, False, None, "REF_TYPE_LIEN"),
            ("entite_source_type", "Type entité source", DataType.STRING, False, False, None, None),
            ("entite_source_id", "ID entité source", DataType.STRING, False, False, None, None),
            ("entite_cible_type", "Type entité cible", DataType.STRING, False, False, None, None),
            ("entite_cible_id", "ID entité cible", DataType.STRING, False, False, None, None),
            ("role", "Rôle", DataType.STRING, False, False, None, None),
            ("quote_part", "Quote-part (%)", DataType.DECIMAL, True, False, None, None),
        ]
        for i, (name, label, dtype, nullable, is_key, dfmt, ref) in enumerate(lien_fields, 1):
            db.add(FieldSpec(
                tech_spec_id=spec_lien.id, field_name=name, field_label=label,
                position=i, data_type=dtype, is_nullable=nullable, is_part_of_key=is_key,
                date_format=dfmt, referentiel_code=ref,
            ))

        # ── Référentiels ──
        referentiels = {
            "REF_PRODUIT": [
                ("PRET_IMMO", "Prêt immobilier"), ("PRET_CONSO", "Prêt consommation"),
                ("CREDIT_BAIL", "Crédit-bail"), ("DECOUVERT", "Découvert"),
                ("PEL", "Plan Épargne Logement"), ("LIVRET_A", "Livret A"),
                ("DAV", "Dépôt à vue"), ("CAT", "Compte à terme"),
            ],
            "REF_TYPE_PRODUIT": [
                ("CREDIT", "Crédit"), ("EPARGNE", "Épargne"), ("DEPOT", "Dépôt"),
            ],
            "REF_DEVISE": [("EUR", "Euro"), ("USD", "Dollar US"), ("GBP", "Livre sterling")],
            "REF_TYPE_TAUX": [("FIXE", "Fixe"), ("VARIABLE", "Variable"), ("REVISABLE", "Révisable")],
            "REF_STATUT_CONTRAT": [
                ("ACTIF", "Actif"), ("CLOTURE", "Clôturé"), ("CONTENTIEUX", "Contentieux"),
            ],
            "REF_TYPE_TIERS": [
                ("PERSONNE_PHYSIQUE", "Personne physique"),
                ("PERSONNE_MORALE", "Personne morale"),
                ("ETABLISSEMENT_CREDIT", "Établissement de crédit"),
            ],
            "REF_PAYS": [("FRA", "France"), ("DEU", "Allemagne"), ("ITA", "Italie"), ("ESP", "Espagne"), ("GBR", "Royaume-Uni")],
            "REF_SEGMENT": [
                ("PARTICULIER", "Particulier"), ("PROFESSIONNEL", "Professionnel"),
                ("PME", "PME"), ("ETI", "ETI"), ("GRANDE_ENTREPRISE", "Grande entreprise"),
            ],
            "REF_ETABLISSEMENT": [("ETB001", "Banque Nationale de Test")],
            "REF_TYPE_TITRE": [("OBLIGATION", "Obligation"), ("ACTION", "Action"), ("OPCVM", "OPCVM"), ("TCN", "TCN")],
            "REF_TYPE_LIEN": [
                ("TITULAIRE", "Titulaire"), ("CO_EMPRUNTEUR", "Co-emprunteur"),
                ("GARANT", "Garant"), ("EMETTEUR", "Émetteur"),
            ],
        }
        for ref_code, values in referentiels.items():
            for val, label in values:
                db.add(RefValue(
                    version_id=version.id, referentiel_code=ref_code,
                    value=val, label=label,
                ))

        # ── Règles fonctionnelles ──
        rules = [
            FuncRule(
                version_id=version.id, table_name=TableName.CONTRAT,
                rule_code="FUNC_CONTRAT_001",
                rule_name="Taux DAR obligatoire si taux fixe",
                description="Si le contrat est un crédit à taux fixe, le taux_dar est obligatoire",
                condition_expr={"and": [
                    {"field": "type_produit", "operator": "eq", "value": "CREDIT"},
                    {"field": "type_taux", "operator": "eq", "value": "FIXE"},
                ]},
                validation_expr={"field": "taux_dar", "operator": "is_not_null"},
                severity=RuleSeverity.BLOCKING,
                error_message="Le taux à la DAR est obligatoire pour un crédit à taux fixe",
            ),
            FuncRule(
                version_id=version.id, table_name=TableName.CONTRAT,
                rule_code="FUNC_CONTRAT_002",
                rule_name="Date échéance obligatoire pour les crédits",
                condition_expr={"field": "type_produit", "operator": "eq", "value": "CREDIT"},
                validation_expr={"field": "date_echeance", "operator": "is_not_null"},
                severity=RuleSeverity.BLOCKING,
                error_message="La date d'échéance est obligatoire pour les crédits",
            ),
            FuncRule(
                version_id=version.id, table_name=TableName.CONTRAT,
                rule_code="FUNC_CONTRAT_003",
                rule_name="Montant initial positif pour contrats actifs",
                condition_expr={"field": "statut_contrat", "operator": "eq", "value": "ACTIF"},
                validation_expr={"field": "montant_initial", "operator": "gt", "value": 0},
                severity=RuleSeverity.BLOCKING,
                error_message="Le montant initial doit être positif pour un contrat actif",
            ),
            FuncRule(
                version_id=version.id, table_name=TableName.CONTRAT,
                rule_code="FUNC_CONTRAT_004",
                rule_name="Montant restant dû positif ou nul",
                condition_expr={"field": "montant_restant_du", "operator": "is_not_null"},
                validation_expr={"field": "montant_restant_du", "operator": "gte", "value": 0},
                severity=RuleSeverity.BLOCKING,
                error_message="Le montant restant dû ne peut pas être négatif",
            ),
            FuncRule(
                version_id=version.id, table_name=TableName.TIERS,
                rule_code="FUNC_TIERS_001",
                rule_name="Raison sociale obligatoire pour personnes morales",
                condition_expr={"field": "type_tiers", "operator": "in",
                                "value": ["PERSONNE_MORALE", "ETABLISSEMENT_CREDIT"]},
                validation_expr={"field": "raison_sociale", "operator": "is_not_null"},
                severity=RuleSeverity.BLOCKING,
                error_message="La raison sociale est obligatoire pour les personnes morales",
            ),
            FuncRule(
                version_id=version.id, table_name=TableName.TIERS,
                rule_code="FUNC_TIERS_002",
                rule_name="Date de défaut obligatoire si en défaut",
                condition_expr={"field": "est_defaut", "operator": "eq", "value": "true"},
                validation_expr={"field": "date_defaut", "operator": "is_not_null"},
                severity=RuleSeverity.BLOCKING,
                error_message="La date de défaut est obligatoire quand le tiers est en défaut",
            ),
            FuncRule(
                version_id=version.id, table_name=TableName.LIEN,
                rule_code="FUNC_LIEN_001",
                rule_name="Quote-part entre 0 et 100",
                condition_expr={"field": "quote_part", "operator": "is_not_null"},
                validation_expr={"field": "quote_part", "operator": "between", "value": [0, 100]},
                severity=RuleSeverity.BLOCKING,
                error_message="La quote-part doit être comprise entre 0 et 100",
            ),
        ]
        for rule in rules:
            db.add(rule)

        # ── Périmètres métier ──

        # Risques : exclut PEL et particuliers
        perim_risques = BusinessPerimeter(
            version_id=version.id, code_metier="RISQUES",
            label="Direction des Risques",
            description="Périmètre risques : exclut PEL et tiers particuliers",
            filter_rules=[
                {"table": "contrat", "field": "code_produit", "operator": "in", "value": ["PEL"]},
                {"table": "tiers", "field": "segment_clientele", "operator": "eq", "value": "PARTICULIER"},
            ],
            cascade_filters=True,
            is_active=True,
        )
        db.add(perim_risques)
        db.flush()

        # Export contrats pour risques
        db.add(ExportSpec(
            perimeter_id=perim_risques.id, table_name=TableName.CONTRAT,
            export_format=ExportFormat.CSV,
            file_name_template="{code_metier}_{etablissement}_{date_arrete}_{table}.csv",
            field_mappings=[
                {"source_field": "identifiant_contrat", "target_name": "ID_CONTRAT", "position": 1},
                {"source_field": "code_produit", "target_name": "PRODUIT", "position": 2},
                {"source_field": "montant_initial", "target_name": "MONTANT_INIT", "position": 3},
                {"source_field": "montant_restant_du", "target_name": "ENCOURS", "position": 4},
                {"source_field": "type_taux", "target_name": "TYPE_TAUX", "position": 5},
                {"source_field": "taux_dar", "target_name": "TAUX", "position": 6},
                {"source_field": "statut_contrat", "target_name": "STATUT", "position": 7},
            ],
        ))

        # Export tiers pour risques
        db.add(ExportSpec(
            perimeter_id=perim_risques.id, table_name=TableName.TIERS,
            export_format=ExportFormat.CSV,
            file_name_template="{code_metier}_{etablissement}_{date_arrete}_{table}.csv",
            field_mappings=[
                {"source_field": "identifiant_tiers", "target_name": "ID_TIERS", "position": 1},
                {"source_field": "type_tiers", "target_name": "TYPE", "position": 2},
                {"source_field": "notation_interne", "target_name": "NOTATION", "position": 3},
                {"source_field": "est_defaut", "target_name": "DEFAUT", "position": 4},
                {"source_field": "date_defaut", "target_name": "DATE_DEFAUT", "position": 5},
            ],
        ))

        # Comptabilité : tous les produits, tous les clients
        perim_compta = BusinessPerimeter(
            version_id=version.id, code_metier="COMPTA",
            label="Direction Comptable",
            description="Périmètre comptable : toutes les données",
            filter_rules=[],
            cascade_filters=False,
            is_active=True,
        )
        db.add(perim_compta)
        db.flush()

        db.add(ExportSpec(
            perimeter_id=perim_compta.id, table_name=TableName.CONTRAT,
            export_format=ExportFormat.CSV,
            file_name_template="{code_metier}_{etablissement}_{date_arrete}_{table}.csv",
            field_mappings=[
                {"source_field": "identifiant_contrat", "target_name": "NUM_CONTRAT", "position": 1},
                {"source_field": "code_produit", "target_name": "CODE_PRODUIT", "position": 2},
                {"source_field": "date_ouverture", "target_name": "DATE_OUVERTURE", "position": 3},
                {"source_field": "montant_initial", "target_name": "MONTANT", "position": 4},
                {"source_field": "devise", "target_name": "DEVISE", "position": 5},
                {"source_field": "statut_contrat", "target_name": "STATUT", "position": 6},
            ],
        ))

        db.commit()
        print("Seed terminé avec succès !")
        print(f"  - Version : {version.code}")
        print(f"  - 4 specs techniques (contrat, tiers, titre, lien)")
        print(f"  - {len(referentiels)} référentiels")
        print(f"  - {len(rules)} règles fonctionnelles")
        print(f"  - 2 périmètres métier (RISQUES, COMPTA)")

    except Exception as e:
        db.rollback()
        print(f"Erreur : {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
