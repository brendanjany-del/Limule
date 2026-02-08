"""Génère des fichiers CSV volumineux pour test de performance.

Usage : python scripts/generate_large_samples.py

Génère pour l'arrêté 31/12/2025, établissement CELC :
  - 300 000 tiers
  - 1 000 000 contrats
  - 150 000 titres
  - ~1 050 000 liens (1 par contrat + co-emprunteurs)
"""

import csv
import os
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "input"

NUM_TIERS = 300_000
NUM_CONTRATS = 1_000_000
NUM_TITRES = 150_000
NUM_CO_EMPRUNTEURS = 50_000

ETB = "CELC"
ARRETE = "202512"
VERSION = "V2024_01"

# Pré-calcul de dates aléatoires pour performance
_base = date(2000, 1, 1)
_range_days = (date(2025, 12, 31) - _base).days


def rand_date(start_year=2000, end_year=2025):
    d = random.randint(0, _range_days)
    return (_base + timedelta(days=d)).isoformat()


def progress(current, total, label):
    if current % 50_000 == 0 or current == total:
        pct = current * 100 // total
        print(f"\r  {label}: {current:>10,} / {total:,} ({pct}%)", end="", flush=True)


def generate_tiers():
    print(f"Génération de {NUM_TIERS:,} tiers...")
    types = ["PERSONNE_PHYSIQUE", "PERSONNE_MORALE", "ETABLISSEMENT_CREDIT"]
    segments = ["PARTICULIER", "PROFESSIONNEL", "PME", "ETI", "GRANDE_ENTREPRISE"]
    pays = ["FRA", "DEU", "ITA", "ESP", "GBR", "BEL", "LUX", "NLD", "CHE", "PRT"]
    notations = ["A1", "A2", "B1", "B2", "C1", "C2", "D", ""]
    naf_codes = [f"{random.randint(10,99)}.{random.randint(10,99)}" for _ in range(200)]

    filepath = OUTPUT_DIR / f"{VERSION}_{ETB}_{ARRETE}_tiers.csv"
    fieldnames = [
        "identifiant_tiers", "type_tiers", "raison_sociale", "code_naf",
        "pays_residence", "segment_clientele", "notation_interne",
        "date_entree_relation", "est_defaut", "date_defaut",
    ]

    errors_injected = 0
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()

        for i in range(1, NUM_TIERS + 1):
            t = random.choice(types)
            is_defaut = random.random() < 0.03
            is_pm = t != "PERSONNE_PHYSIQUE"

            row = {
                "identifiant_tiers": f"T{i:07d}",
                "type_tiers": t,
                "raison_sociale": f"Entreprise {i}" if is_pm else "",
                "code_naf": random.choice(naf_codes) if is_pm else "",
                "pays_residence": random.choice(pays),
                "segment_clientele": random.choice(segments),
                "notation_interne": random.choice(notations),
                "date_entree_relation": rand_date(2000, 2024),
                "est_defaut": "true" if is_defaut else "false",
                "date_defaut": rand_date(2020, 2025) if is_defaut else "",
            }

            # Erreurs intentionnelles (~0.1%)
            if i % 1000 == 10:
                row["type_tiers"] = "PERSONNE_MORALE"
                row["raison_sociale"] = ""  # PM sans raison sociale
                errors_injected += 1
            elif i % 1000 == 20:
                row["est_defaut"] = "true"
                row["date_defaut"] = ""  # Défaut sans date
                errors_injected += 1

            writer.writerow(row)
            progress(i, NUM_TIERS, "tiers")

    print(f"\n  -> {filepath.name} ({NUM_TIERS:,} lignes, {errors_injected} erreurs injectées)")
    return filepath


def generate_contrats():
    print(f"\nGénération de {NUM_CONTRATS:,} contrats...")
    produits_credit = ["PRET_IMMO", "PRET_CONSO", "CREDIT_BAIL", "DECOUVERT"]
    produits_epargne = ["PEL", "LIVRET_A"]
    produits_depot = ["DAV", "CAT"]
    all_produits = produits_credit + produits_epargne + produits_depot
    types_taux = ["FIXE", "VARIABLE", "REVISABLE"]
    statuts = ["ACTIF", "ACTIF", "ACTIF", "ACTIF", "CLOTURE", "CONTENTIEUX"]
    devises = ["EUR", "EUR", "EUR", "EUR", "EUR", "USD", "GBP", "CHF"]
    segments = ["PARTICULIER", "PROFESSIONNEL", "PME", "ETI", "GRANDE_ENTREPRISE"]
    durees = [12, 24, 36, 60, 84, 120, 180, 240, 300]

    filepath = OUTPUT_DIR / f"{VERSION}_{ETB}_{ARRETE}_contrat.csv"
    fieldnames = [
        "identifiant_contrat", "code_etablissement", "code_produit", "type_produit",
        "date_ouverture", "date_echeance", "montant_initial", "montant_restant_du",
        "devise", "type_taux", "taux_dar", "duree_initiale_mois",
        "identifiant_tiers", "statut_contrat", "segment_clientele",
    ]

    errors_injected = 0
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()

        for i in range(1, NUM_CONTRATS + 1):
            prod = random.choice(all_produits)
            if prod in produits_credit:
                tp = "CREDIT"
            elif prod in produits_epargne:
                tp = "EPARGNE"
            else:
                tp = "DEPOT"

            is_credit = tp == "CREDIT"
            type_taux = random.choice(types_taux) if is_credit else ""
            is_fixe = type_taux == "FIXE"
            montant = round(random.uniform(500, 800_000), 2)
            tiers_id = f"T{random.randint(1, NUM_TIERS):07d}"

            row = {
                "identifiant_contrat": f"C{i:08d}",
                "code_etablissement": ETB,
                "code_produit": prod,
                "type_produit": tp,
                "date_ouverture": rand_date(2010, 2025),
                "date_echeance": rand_date(2025, 2045) if is_credit else "",
                "montant_initial": str(montant),
                "montant_restant_du": str(round(montant * random.uniform(0.05, 0.95), 2)) if is_credit else "",
                "devise": random.choice(devises),
                "type_taux": type_taux,
                "taux_dar": str(round(random.uniform(0.3, 6.0), 4)) if is_fixe else "",
                "duree_initiale_mois": str(random.choice(durees)) if is_credit else "",
                "identifiant_tiers": tiers_id,
                "statut_contrat": random.choice(statuts),
                "segment_clientele": random.choice(segments),
            }

            # Erreurs intentionnelles (~0.1%)
            if i % 2000 == 5:
                row["code_produit"] = "PRET_IMMO"
                row["type_taux"] = "FIXE"
                row["taux_dar"] = ""  # Fixe sans taux
                errors_injected += 1
            elif i % 2000 == 15:
                row["type_produit"] = "CREDIT"
                row["date_echeance"] = ""  # Crédit sans échéance
                errors_injected += 1
            elif i % 5000 == 25:
                row["montant_restant_du"] = "-1500.00"  # Montant négatif
                errors_injected += 1
            elif i % 5000 == 35:
                row["devise"] = "XXX"  # Devise inconnue
                errors_injected += 1

            writer.writerow(row)
            progress(i, NUM_CONTRATS, "contrats")

    print(f"\n  -> {filepath.name} ({NUM_CONTRATS:,} lignes, {errors_injected} erreurs injectées)")
    return filepath


def generate_titres():
    print(f"\nGénération de {NUM_TITRES:,} titres...")
    types = ["OBLIGATION", "ACTION", "OPCVM", "TCN"]
    devises = ["EUR", "EUR", "EUR", "USD", "GBP", "CHF", "JPY"]

    filepath = OUTPUT_DIR / f"{VERSION}_{ETB}_{ARRETE}_titre.csv"
    fieldnames = [
        "identifiant_titre", "code_isin", "type_titre", "emetteur",
        "valeur_nominale", "valeur_marche", "devise",
        "date_emission", "date_maturite",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()

        for i in range(1, NUM_TITRES + 1):
            writer.writerow({
                "identifiant_titre": f"TI{i:07d}",
                "code_isin": f"FR{random.randint(1000000000, 9999999999)}",
                "type_titre": random.choice(types),
                "emetteur": f"T{random.randint(1, NUM_TIERS):07d}",
                "valeur_nominale": str(round(random.uniform(100, 50_000), 2)),
                "valeur_marche": str(round(random.uniform(80, 55_000), 2)),
                "devise": random.choice(devises),
                "date_emission": rand_date(2005, 2024),
                "date_maturite": rand_date(2025, 2040),
            })
            progress(i, NUM_TITRES, "titres")

    print(f"\n  -> {filepath.name} ({NUM_TITRES:,} lignes)")
    return filepath


def generate_liens():
    total = NUM_CONTRATS + NUM_CO_EMPRUNTEURS
    print(f"\nGénération de {total:,} liens...")

    filepath = OUTPUT_DIR / f"{VERSION}_{ETB}_{ARRETE}_lien.csv"
    fieldnames = [
        "identifiant_lien", "type_lien", "entite_source_type", "entite_source_id",
        "entite_cible_type", "entite_cible_id", "role", "quote_part",
    ]

    errors_injected = 0
    idx = 0
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()

        # Un lien TITULAIRE par contrat
        for i in range(1, NUM_CONTRATS + 1):
            idx += 1
            writer.writerow({
                "identifiant_lien": f"L{idx:08d}",
                "type_lien": "TITULAIRE",
                "entite_source_type": "contrat",
                "entite_source_id": f"C{i:08d}",
                "entite_cible_type": "tiers",
                "entite_cible_id": f"T{random.randint(1, NUM_TIERS):07d}",
                "role": "TITULAIRE",
                "quote_part": "100",
            })
            progress(idx, total, "liens")

        # Co-emprunteurs sur les premiers contrats
        for i in range(1, NUM_CO_EMPRUNTEURS + 1):
            idx += 1
            qp = "50"
            # Erreur intentionnelle : quote-part > 100
            if i % 10_000 == 1:
                qp = "150"
                errors_injected += 1

            writer.writerow({
                "identifiant_lien": f"L{idx:08d}",
                "type_lien": "CO_EMPRUNTEUR",
                "entite_source_type": "contrat",
                "entite_source_id": f"C{i:08d}",
                "entite_cible_type": "tiers",
                "entite_cible_id": f"T{random.randint(1, NUM_TIERS):07d}",
                "role": "CO_EMPRUNTEUR",
                "quote_part": qp,
            })
            progress(idx, total, "liens")

    print(f"\n  -> {filepath.name} ({total:,} lignes, {errors_injected} erreurs injectées)")
    return filepath


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"=== Génération données volumétriques ===")
    print(f"Établissement : {ETB}")
    print(f"Arrêté : {ARRETE}")
    print(f"Destination : {OUTPUT_DIR}\n")

    t0 = time.time()
    generate_tiers()
    generate_contrats()
    generate_titres()
    generate_liens()

    elapsed = time.time() - t0
    print(f"\n=== Terminé en {elapsed:.1f}s ===")

    # Afficher les tailles de fichiers
    total_size = 0
    for f in sorted(OUTPUT_DIR.glob(f"{VERSION}_{ETB}_*")):
        size = f.stat().st_size
        total_size += size
        print(f"  {f.name}: {size / 1024 / 1024:.1f} MB")
    print(f"  Total: {total_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
