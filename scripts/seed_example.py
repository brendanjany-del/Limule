"""Script de seed : crée une version de spécifications complète pour la banque réglementaire.

Usage : python -m scripts.seed_example
Requiert une BDD PostgreSQL accessible.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SyncSessionLocal, sync_engine, Base
from app.models.specification import (
    SpecVersion, TechSpec, FieldSpec, FuncRule, RefValue,
    BusinessPerimeter, ExportSpec,
    TableName, FileFormat, DataType, RuleSeverity, ExportFormat,
)
from app.models.processing import Etablissement

# Importer tous les modèles
from app.models import specification, processing, data  # noqa


def seed():
    # Créer les tables
    Base.metadata.create_all(sync_engine)

    db = SyncSessionLocal()
    try:
        # Vérifier si déjà seedé
        if db.query(SpecVersion).filter(SpecVersion.code == "V2024_01").first():
            print("Base déjà alimentée. Skipping.")
            return

        # ── Version ──
        version = SpecVersion(
            code="V2024_01",
            label="Version Janvier 2024",
            description="Première version des spécifications réglementaires bancaires",
            created_by="admin",
        )
        db.add(version)
        db.flush()

        # ── Établissements ──
        etb1 = Etablissement(code="ETB001", name="Banque Nationale de Paris", reseau_code="RESEAU_A")
        etb2 = Etablissement(code="ETB002", name="Caisse Régionale du Sud", reseau_code="RESEAU_A")
        etb3 = Etablissement(code="ETB003", name="Crédit Mutuel Nord", reseau_code="RESEAU_B")
        db.add_all([etb1, etb2, etb3])
        db.flush()

        # ══════════════════════════════════════════
        # SPÉCIFICATIONS TECHNIQUES
        # ══════════════════════════════════════════

        # -- Table CONTRAT --
        spec_contrat = TechSpec(
            version_id=version.id,
            table_name=TableName.CONTRAT,
            file_format=FileFormat.CSV,
            separator=";",
            encoding="utf-8",
            has_header=True,
            file_name_pattern=r".*_contrat\.csv$",
            description="Fichier des contrats bancaires",
        )
        db.add(spec_contrat)
        db.flush()

        contrat_fields = [
            ("identifiant_contrat", "Identifiant du contrat", DataType.STRING, False, True, 50, None),
            ("code_etablissement", "Code établissement", DataType.STRING, False, True, 10, "REF_ETABLISSEMENT"),
            ("code_produit", "Code produit", DataType.STRING, False, False, 20, "REF_PRODUIT"),
            ("type_produit", "Type de produit", DataType.STRING, False, False, 50, "REF_TYPE_PRODUIT"),
            ("date_ouverture", "Date d'ouverture", DataType.DATE, False, False, None, None),
            ("date_echeance", "Date d'échéance", DataType.DATE, True, False, None, None),
            ("montant_initial", "Montant initial", DataType.DECIMAL, False, False, None, None),
            ("montant_restant_du", "Capital restant dû", DataType.DECIMAL, True, False, None, None),
            ("devise", "Code devise", DataType.STRING, False, False, 3, "REF_DEVISE"),
            ("type_taux", "Type de taux", DataType.STRING, True, False, 20, "REF_TYPE_TAUX"),
            ("taux_dar", "Taux à la date d'arrêté", DataType.DECIMAL, True, False, None, None),
            ("duree_initiale_mois", "Durée initiale en mois", DataType.INTEGER, True, False, None, None),
            ("identifiant_tiers", "Identifiant du tiers titulaire", DataType.STRING, False, False, 50, None),
            ("statut_contrat", "Statut du contrat", DataType.STRING, False, False, 20, "REF_STATUT_CONTRAT"),
            ("segment_clientele", "Segment clientèle", DataType.STRING, True, False, 30, "REF_SEGMENT"),
        ]
        for pos, (name, label, dtype, nullable, is_key, maxlen, ref) in enumerate(contrat_fields, 1):
            db.add(FieldSpec(
                tech_spec_id=spec_contrat.id, field_name=name, field_label=label,
                position=pos, data_type=dtype, date_format="%Y-%m-%d",
                is_nullable=nullable, is_part_of_key=is_key,
                max_length=maxlen, referentiel_code=ref,
            ))

        # -- Table TIERS --
        spec_tiers = TechSpec(
            version_id=version.id,
            table_name=TableName.TIERS,
            file_format=FileFormat.CSV,
            separator=";",
            encoding="utf-8",
            has_header=True,
            file_name_pattern=r".*_tiers\.csv$",
            description="Fichier des tiers (clients, contreparties)",
        )
        db.add(spec_tiers)
        db.flush()

        tiers_fields = [
            ("identifiant_tiers", "Identifiant du tiers", DataType.STRING, False, True, 50, None),
            ("type_tiers", "Type de tiers", DataType.STRING, False, False, 30, "REF_TYPE_TIERS"),
            ("raison_sociale", "Raison sociale / Nom", DataType.STRING, True, False, 300, None),
            ("code_naf", "Code NAF/APE", DataType.STRING, True, False, 10, None),
            ("pays_residence", "Pays de résidence", DataType.STRING, False, False, 3, "REF_PAYS"),
            ("segment_clientele", "Segment clientèle", DataType.STRING, True, False, 30, "REF_SEGMENT"),
            ("notation_interne", "Notation interne", DataType.STRING, True, False, 10, None),
            ("date_entree_relation", "Date entrée en relation", DataType.DATE, True, False, None, None),
            ("est_defaut", "En défaut (O/N)", DataType.BOOLEAN, True, False, None, None),
            ("date_defaut", "Date de défaut", DataType.DATE, True, False, None, None),
        ]
        for pos, (name, label, dtype, nullable, is_key, maxlen, ref) in enumerate(tiers_fields, 1):
            db.add(FieldSpec(
                tech_spec_id=spec_tiers.id, field_name=name, field_label=label,
                position=pos, data_type=dtype, date_format="%Y-%m-%d",
                is_nullable=nullable, is_part_of_key=is_key,
                max_length=maxlen, referentiel_code=ref,
            ))

        # -- Table TITRE --
        spec_titre = TechSpec(
            version_id=version.id,
            table_name=TableName.TITRE,
            file_format=FileFormat.CSV,
            separator=";",
            encoding="utf-8",
            has_header=True,
            file_name_pattern=r".*_titre\.csv$",
            description="Fichier des titres et valeurs mobilières",
        )
        db.add(spec_titre)
        db.flush()

        titre_fields = [
            ("identifiant_titre", "Identifiant du titre", DataType.STRING, False, True, 50, None),
            ("code_isin", "Code ISIN", DataType.STRING, True, False, 12, None),
            ("type_titre", "Type de titre", DataType.STRING, False, False, 30, "REF_TYPE_TITRE"),
            ("emetteur", "Identifiant émetteur", DataType.STRING, True, False, 50, None),
            ("valeur_nominale", "Valeur nominale", DataType.DECIMAL, True, False, None, None),
            ("valeur_marche", "Valeur de marché", DataType.DECIMAL, True, False, None, None),
            ("devise", "Code devise", DataType.STRING, False, False, 3, "REF_DEVISE"),
            ("date_emission", "Date d'émission", DataType.DATE, True, False, None, None),
            ("date_maturite", "Date de maturité", DataType.DATE, True, False, None, None),
        ]
        for pos, (name, label, dtype, nullable, is_key, maxlen, ref) in enumerate(titre_fields, 1):
            db.add(FieldSpec(
                tech_spec_id=spec_titre.id, field_name=name, field_label=label,
                position=pos, data_type=dtype, date_format="%Y-%m-%d",
                is_nullable=nullable, is_part_of_key=is_key,
                max_length=maxlen, referentiel_code=ref,
            ))

        # -- Table LIEN --
        spec_lien = TechSpec(
            version_id=version.id,
            table_name=TableName.LIEN,
            file_format=FileFormat.CSV,
            separator=";",
            encoding="utf-8",
            has_header=True,
            file_name_pattern=r".*_lien\.csv$",
            description="Fichier des liens entre entités (contrat-tiers, contrat-titre, etc.)",
        )
        db.add(spec_lien)
        db.flush()

        lien_fields = [
            ("identifiant_lien", "Identifiant du lien", DataType.STRING, False, True, 100, None),
            ("type_lien", "Type de lien", DataType.STRING, False, False, 30, "REF_TYPE_LIEN"),
            ("entite_source_type", "Type entité source", DataType.STRING, False, False, 20, None),
            ("entite_source_id", "ID entité source", DataType.STRING, False, False, 50, None),
            ("entite_cible_type", "Type entité cible", DataType.STRING, False, False, 20, None),
            ("entite_cible_id", "ID entité cible", DataType.STRING, False, False, 50, None),
            ("role", "Rôle dans la relation", DataType.STRING, True, False, 50, None),
            ("quote_part", "Quote-part (%)", DataType.DECIMAL, True, False, None, None),
        ]
        for pos, (name, label, dtype, nullable, is_key, maxlen, ref) in enumerate(lien_fields, 1):
            db.add(FieldSpec(
                tech_spec_id=spec_lien.id, field_name=name, field_label=label,
                position=pos, data_type=dtype,
                is_nullable=nullable, is_part_of_key=is_key,
                max_length=maxlen, referentiel_code=ref,
            ))

        # ══════════════════════════════════════════
        # RÉFÉRENTIELS
        # ══════════════════════════════════════════

        referentiels = {
            "REF_PRODUIT": [
                ("PRET_IMMO", "Prêt immobilier"), ("PRET_CONSO", "Prêt à la consommation"),
                ("CREDIT_BAIL", "Crédit-bail"), ("DECOUVERT", "Découvert"),
                ("PEL", "Plan Épargne Logement"), ("CEL", "Compte Épargne Logement"),
                ("LIVRET_A", "Livret A"), ("CAT", "Compte à terme"),
                ("DAV", "Dépôt à vue"), ("AFFACTURAGE", "Affacturage"),
            ],
            "REF_TYPE_PRODUIT": [
                ("CREDIT", "Crédit"), ("EPARGNE", "Épargne"),
                ("DEPOT", "Dépôt"), ("GARANTIE", "Garantie"),
                ("HORS_BILAN", "Hors bilan"),
            ],
            "REF_DEVISE": [
                ("EUR", "Euro"), ("USD", "Dollar US"), ("GBP", "Livre sterling"),
                ("CHF", "Franc suisse"), ("JPY", "Yen"),
            ],
            "REF_TYPE_TAUX": [
                ("FIXE", "Taux fixe"), ("VARIABLE", "Taux variable"),
                ("REVISABLE", "Taux révisable"), ("MIXTE", "Taux mixte"),
            ],
            "REF_STATUT_CONTRAT": [
                ("ACTIF", "Actif"), ("CLOTURE", "Clôturé"),
                ("CONTENTIEUX", "En contentieux"), ("DEFAUT", "En défaut"),
            ],
            "REF_SEGMENT": [
                ("PARTICULIER", "Particulier"), ("PROFESSIONNEL", "Professionnel"),
                ("PME", "PME"), ("ETI", "ETI"), ("GRANDE_ENTREPRISE", "Grande entreprise"),
                ("INSTITUTIONNEL", "Institutionnel"), ("SOUVERAIN", "Souverain"),
            ],
            "REF_TYPE_TIERS": [
                ("PERSONNE_PHYSIQUE", "Personne physique"),
                ("PERSONNE_MORALE", "Personne morale"),
                ("ETABLISSEMENT_CREDIT", "Établissement de crédit"),
                ("ASSURANCE", "Assurance"), ("FONDS", "Fonds"),
            ],
            "REF_PAYS": [
                ("FRA", "France"), ("DEU", "Allemagne"), ("ITA", "Italie"),
                ("ESP", "Espagne"), ("GBR", "Royaume-Uni"), ("USA", "États-Unis"),
                ("CHE", "Suisse"), ("LUX", "Luxembourg"), ("BEL", "Belgique"),
            ],
            "REF_TYPE_TITRE": [
                ("OBLIGATION", "Obligation"), ("ACTION", "Action"),
                ("OPCVM", "OPCVM"), ("TCN", "Titre de créance négociable"),
                ("ABS", "Asset-Backed Security"),
            ],
            "REF_TYPE_LIEN": [
                ("TITULAIRE", "Titulaire"), ("CO_EMPRUNTEUR", "Co-emprunteur"),
                ("GARANT", "Garant"), ("BENEFICIAIRE", "Bénéficiaire"),
                ("DETENTEUR", "Détenteur"),
            ],
            "REF_ETABLISSEMENT": [
                ("ETB001", "Banque Nationale de Paris"),
                ("ETB002", "Caisse Régionale du Sud"),
                ("ETB003", "Crédit Mutuel Nord"),
            ],
        }

        for ref_code, values in referentiels.items():
            for val, label in values:
                db.add(RefValue(
                    version_id=version.id,
                    referentiel_code=ref_code,
                    value=val,
                    label=label,
                ))

        # ══════════════════════════════════════════
        # RÈGLES FONCTIONNELLES
        # ══════════════════════════════════════════

        rules = [
            # Contrats
            FuncRule(
                version_id=version.id,
                table_name=TableName.CONTRAT,
                rule_code="FUNC_CONTRAT_001",
                rule_name="Taux DAR obligatoire pour prêts à taux fixe",
                description="Si le contrat est un prêt immobilier ou conso et le type de taux est FIXE, le taux_dar est obligatoire",
                condition_expr={
                    "and": [
                        {"field": "code_produit", "operator": "in", "value": ["PRET_IMMO", "PRET_CONSO"]},
                        {"field": "type_taux", "operator": "eq", "value": "FIXE"},
                    ]
                },
                validation_expr={"field": "taux_dar", "operator": "is_not_null"},
                severity=RuleSeverity.BLOCKING,
                error_message="Le taux à la DAR est obligatoire pour les prêts à taux fixe",
            ),
            FuncRule(
                version_id=version.id,
                table_name=TableName.CONTRAT,
                rule_code="FUNC_CONTRAT_002",
                rule_name="Date échéance obligatoire pour les crédits",
                condition_expr={"field": "type_produit", "operator": "eq", "value": "CREDIT"},
                validation_expr={"field": "date_echeance", "operator": "is_not_null"},
                severity=RuleSeverity.BLOCKING,
                error_message="La date d'échéance est obligatoire pour les produits de type crédit",
            ),
            FuncRule(
                version_id=version.id,
                table_name=TableName.CONTRAT,
                rule_code="FUNC_CONTRAT_003",
                rule_name="Montant restant dû cohérent",
                condition_expr={"field": "montant_restant_du", "operator": "is_not_null"},
                validation_expr={"field": "montant_restant_du", "operator": "gte", "value": "0"},
                severity=RuleSeverity.BLOCKING,
                error_message="Le montant restant dû ne peut pas être négatif",
            ),
            FuncRule(
                version_id=version.id,
                table_name=TableName.CONTRAT,
                rule_code="FUNC_CONTRAT_004",
                rule_name="Durée initiale obligatoire pour les prêts",
                condition_expr={"field": "code_produit", "operator": "in", "value": ["PRET_IMMO", "PRET_CONSO"]},
                validation_expr={"field": "duree_initiale_mois", "operator": "is_not_null"},
                severity=RuleSeverity.WARNING,
                error_message="La durée initiale devrait être renseignée pour les prêts",
            ),
            FuncRule(
                version_id=version.id,
                table_name=TableName.CONTRAT,
                rule_code="FUNC_CONTRAT_005",
                rule_name="Contrat actif doit avoir un montant initial positif",
                condition_expr={"field": "statut_contrat", "operator": "eq", "value": "ACTIF"},
                validation_expr={"field": "montant_initial", "operator": "gt", "value": "0"},
                severity=RuleSeverity.BLOCKING,
                error_message="Un contrat actif doit avoir un montant initial strictement positif",
            ),

            # Tiers
            FuncRule(
                version_id=version.id,
                table_name=TableName.TIERS,
                rule_code="FUNC_TIERS_001",
                rule_name="Raison sociale obligatoire pour les personnes morales",
                condition_expr={"field": "type_tiers", "operator": "neq", "value": "PERSONNE_PHYSIQUE"},
                validation_expr={"field": "raison_sociale", "operator": "is_not_null"},
                severity=RuleSeverity.BLOCKING,
                error_message="La raison sociale est obligatoire pour les personnes morales",
            ),
            FuncRule(
                version_id=version.id,
                table_name=TableName.TIERS,
                rule_code="FUNC_TIERS_002",
                rule_name="Date de défaut obligatoire si en défaut",
                condition_expr={"field": "est_defaut", "operator": "in", "value": ["true", "1", "oui", "O"]},
                validation_expr={"field": "date_defaut", "operator": "is_not_null"},
                severity=RuleSeverity.BLOCKING,
                error_message="La date de défaut est obligatoire si le tiers est en défaut",
            ),

            # Liens
            FuncRule(
                version_id=version.id,
                table_name=TableName.LIEN,
                rule_code="FUNC_LIEN_001",
                rule_name="Quote-part entre 0 et 100",
                condition_expr={"field": "quote_part", "operator": "is_not_null"},
                validation_expr={"field": "quote_part", "operator": "between", "value": ["0", "100"]},
                severity=RuleSeverity.BLOCKING,
                error_message="La quote-part doit être comprise entre 0 et 100%",
            ),
        ]
        db.add_all(rules)

        # ══════════════════════════════════════════
        # PÉRIMÈTRES MÉTIER
        # ══════════════════════════════════════════

        # Périmètre Risques
        perim_risques = BusinessPerimeter(
            version_id=version.id,
            code_metier="RISQUES",
            label="Direction des Risques",
            description="Périmètre d'export pour la direction des risques - Exclut PEL et particuliers",
            filter_rules=[
                {"table": "contrat", "field": "code_produit", "operator": "in", "value": ["PEL", "CEL"]},
                {"table": "tiers", "field": "segment_clientele", "operator": "eq", "value": "PARTICULIER"},
            ],
            etablissement_filter=None,  # Tous les établissements
            cascade_filters=True,
        )
        db.add(perim_risques)
        db.flush()

        # Exports pour Risques
        for table in [TableName.CONTRAT, TableName.TIERS, TableName.LIEN]:
            field_mappings = []
            spec = db.query(TechSpec).filter(
                TechSpec.version_id == version.id,
                TechSpec.table_name == table,
            ).first()
            if spec:
                for f in sorted(spec.fields, key=lambda x: x.position):
                    field_mappings.append({
                        "source_field": f.field_name,
                        "target_name": f.field_name.upper(),
                        "position": f.position,
                    })

            db.add(ExportSpec(
                perimeter_id=perim_risques.id,
                table_name=table,
                export_format=ExportFormat.CSV,
                file_name_template=f"RISQUES_{table.value}_{{date_arrete}}_{{etablissement}}.csv",
                separator=";",
                include_header=True,
                field_mappings=field_mappings,
            ))

        # Périmètre Comptabilité
        perim_compta = BusinessPerimeter(
            version_id=version.id,
            code_metier="COMPTA",
            label="Comptabilité",
            description="Périmètre d'export comptable - Tous les contrats et tiers",
            filter_rules=[],
            etablissement_filter=None,
            cascade_filters=False,
        )
        db.add(perim_compta)
        db.flush()

        for table in [TableName.CONTRAT, TableName.TIERS]:
            spec = db.query(TechSpec).filter(
                TechSpec.version_id == version.id,
                TechSpec.table_name == table,
            ).first()
            field_mappings = []
            if spec:
                for f in sorted(spec.fields, key=lambda x: x.position):
                    field_mappings.append({
                        "source_field": f.field_name,
                        "target_name": f.field_name.upper(),
                        "position": f.position,
                    })

            db.add(ExportSpec(
                perimeter_id=perim_compta.id,
                table_name=table,
                export_format=ExportFormat.CSV,
                file_name_template=f"COMPTA_{table.value}_{{date_arrete}}_{{etablissement}}.csv",
                separator="|",
                include_header=True,
                field_mappings=field_mappings,
            ))

        db.commit()
        print("Seed terminé avec succès !")
        print(f"  - Version : {version.code}")
        print(f"  - {len(contrat_fields)} champs contrat, {len(tiers_fields)} champs tiers, "
              f"{len(titre_fields)} champs titre, {len(lien_fields)} champs lien")
        print(f"  - {sum(len(v) for v in referentiels.values())} valeurs de référentiel")
        print(f"  - {len(rules)} règles fonctionnelles")
        print(f"  - 2 périmètres métier (RISQUES, COMPTA)")
        print(f"  - 3 établissements")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
