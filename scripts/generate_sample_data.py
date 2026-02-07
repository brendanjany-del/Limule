"""Génère des fichiers CSV d'exemple pour tester le pipeline.

Usage : python -m scripts.generate_sample_data
Génère 4 fichiers dans data/input/ au format attendu par la version V2024_01.
"""

import csv
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "input"
NUM_CONTRATS = 1000
NUM_TIERS = 500


def rand_date(start_year=2015, end_year=2024):
    start = date(start_year, 1, 1)
    delta = (date(end_year, 12, 31) - start).days
    return (start + timedelta(days=random.randint(0, delta))).isoformat()


def generate_tiers():
    """Génère le fichier tiers."""
    types = ["PERSONNE_PHYSIQUE", "PERSONNE_MORALE", "ETABLISSEMENT_CREDIT"]
    segments = ["PARTICULIER", "PROFESSIONNEL", "PME", "ETI", "GRANDE_ENTREPRISE"]
    pays = ["FRA", "DEU", "ITA", "ESP", "GBR"]

    rows = []
    for i in range(1, NUM_TIERS + 1):
        t = random.choice(types)
        is_defaut = random.random() < 0.05
        rows.append({
            "identifiant_tiers": f"T{i:06d}",
            "type_tiers": t,
            "raison_sociale": f"Client {i}" if t != "PERSONNE_PHYSIQUE" else "",
            "code_naf": f"{random.randint(10,99)}.{random.randint(10,99)}" if t != "PERSONNE_PHYSIQUE" else "",
            "pays_residence": random.choice(pays),
            "segment_clientele": random.choice(segments),
            "notation_interne": random.choice(["A1", "A2", "B1", "B2", "C1", "C2", "D", ""]),
            "date_entree_relation": rand_date(2000, 2023),
            "est_defaut": "true" if is_defaut else "false",
            "date_defaut": rand_date(2020, 2024) if is_defaut else "",
        })

    # Injecter quelques erreurs pour les tests
    # Personne morale sans raison sociale
    rows[10]["type_tiers"] = "PERSONNE_MORALE"
    rows[10]["raison_sociale"] = ""

    # Défaut sans date
    rows[20]["est_defaut"] = "true"
    rows[20]["date_defaut"] = ""

    filepath = OUTPUT_DIR / "V2024_01_ETB001_202401_tiers.csv"
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Généré : {filepath} ({len(rows)} lignes)")
    return rows


def generate_contrats(tiers_rows):
    """Génère le fichier contrats."""
    produits = ["PRET_IMMO", "PRET_CONSO", "CREDIT_BAIL", "DECOUVERT", "PEL", "LIVRET_A", "DAV", "CAT"]
    types_produit = {"PRET_IMMO": "CREDIT", "PRET_CONSO": "CREDIT", "CREDIT_BAIL": "CREDIT",
                     "DECOUVERT": "CREDIT", "PEL": "EPARGNE", "LIVRET_A": "EPARGNE",
                     "DAV": "DEPOT", "CAT": "DEPOT"}
    types_taux = ["FIXE", "VARIABLE", "REVISABLE"]
    statuts = ["ACTIF", "ACTIF", "ACTIF", "CLOTURE", "CONTENTIEUX"]

    rows = []
    tiers_ids = [t["identifiant_tiers"] for t in tiers_rows]

    for i in range(1, NUM_CONTRATS + 1):
        prod = random.choice(produits)
        tp = types_produit[prod]
        type_taux = random.choice(types_taux) if tp == "CREDIT" else ""
        is_fixe = type_taux == "FIXE"
        montant = round(random.uniform(1000, 500000), 2)

        rows.append({
            "identifiant_contrat": f"C{i:06d}",
            "code_etablissement": "ETB001",
            "code_produit": prod,
            "type_produit": tp,
            "date_ouverture": rand_date(2015, 2023),
            "date_echeance": rand_date(2024, 2040) if tp == "CREDIT" else "",
            "montant_initial": str(montant),
            "montant_restant_du": str(round(montant * random.uniform(0.1, 0.9), 2)) if tp == "CREDIT" else "",
            "devise": "EUR",
            "type_taux": type_taux,
            "taux_dar": str(round(random.uniform(0.5, 5.0), 4)) if is_fixe else "",
            "duree_initiale_mois": str(random.choice([60, 120, 180, 240, 300])) if tp == "CREDIT" else "",
            "identifiant_tiers": random.choice(tiers_ids),
            "statut_contrat": random.choice(statuts),
            "segment_clientele": random.choice(["PARTICULIER", "PME", "ETI", ""]),
        })

    # Injecter des erreurs
    # Prêt immobilier à taux fixe sans taux_dar
    rows[5]["code_produit"] = "PRET_IMMO"
    rows[5]["type_taux"] = "FIXE"
    rows[5]["taux_dar"] = ""

    # Crédit sans date d'échéance
    rows[15]["type_produit"] = "CREDIT"
    rows[15]["date_echeance"] = ""

    # Montant restant dû négatif
    rows[25]["montant_restant_du"] = "-1500.00"

    # Contrat actif avec montant initial à 0
    rows[35]["statut_contrat"] = "ACTIF"
    rows[35]["montant_initial"] = "0"

    # Type incorrect (valeur hors référentiel)
    rows[45]["devise"] = "XXX"

    filepath = OUTPUT_DIR / "V2024_01_ETB001_202401_contrat.csv"
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Généré : {filepath} ({len(rows)} lignes)")
    return rows


def generate_titres():
    """Génère le fichier titres."""
    types = ["OBLIGATION", "ACTION", "OPCVM", "TCN"]
    rows = []
    for i in range(1, 201):
        rows.append({
            "identifiant_titre": f"TI{i:06d}",
            "code_isin": f"FR00{random.randint(10000000, 99999999)}",
            "type_titre": random.choice(types),
            "emetteur": f"T{random.randint(1, NUM_TIERS):06d}",
            "valeur_nominale": str(round(random.uniform(100, 10000), 2)),
            "valeur_marche": str(round(random.uniform(80, 12000), 2)),
            "devise": "EUR",
            "date_emission": rand_date(2010, 2023),
            "date_maturite": rand_date(2024, 2035),
        })

    filepath = OUTPUT_DIR / "V2024_01_ETB001_202401_titre.csv"
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Généré : {filepath} ({len(rows)} lignes)")


def generate_liens(contrat_rows, tiers_rows):
    """Génère le fichier liens."""
    rows = []
    for i, c in enumerate(contrat_rows):
        rows.append({
            "identifiant_lien": f"L{i+1:06d}",
            "type_lien": "TITULAIRE",
            "entite_source_type": "contrat",
            "entite_source_id": c["identifiant_contrat"],
            "entite_cible_type": "tiers",
            "entite_cible_id": c["identifiant_tiers"],
            "role": "TITULAIRE",
            "quote_part": "100",
        })

    # Quelques co-emprunteurs
    for i in range(50):
        rows.append({
            "identifiant_lien": f"L{NUM_CONTRATS + i + 1:06d}",
            "type_lien": "CO_EMPRUNTEUR",
            "entite_source_type": "contrat",
            "entite_source_id": contrat_rows[i]["identifiant_contrat"],
            "entite_cible_type": "tiers",
            "entite_cible_id": f"T{random.randint(1, NUM_TIERS):06d}",
            "role": "CO_EMPRUNTEUR",
            "quote_part": "50",
        })

    # Quote-part invalide
    rows[-1]["quote_part"] = "150"

    filepath = OUTPUT_DIR / "V2024_01_ETB001_202401_lien.csv"
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Généré : {filepath} ({len(rows)} lignes)")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tiers = generate_tiers()
    contrats = generate_contrats(tiers)
    generate_titres()
    generate_liens(contrats, tiers)
    print(f"\nFichiers générés dans {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
