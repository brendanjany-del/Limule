"""Upload les fichiers d'exemple via l'API locale."""
import httpx
import os
import sys

BASE = "http://localhost:8000"

files = [
    ("tiers", "V2024_01_ETB001_202401_tiers.csv"),
    ("contrats", "V2024_01_ETB001_202401_contrat.csv"),
    ("titres", "V2024_01_ETB001_202401_titre.csv"),
    ("liens", "V2024_01_ETB001_202401_lien.csv"),
]

data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "input")

for table, f in files:
    path = os.path.join(data_dir, f)
    if not os.path.exists(path):
        print(f"FICHIER MANQUANT: {path}")
        continue
    print(f"Upload {table} ({f})...")
    with open(path, "rb") as fh:
        r = httpx.post(
            f"{BASE}/api/flux/upload",
            data={
                "etablissement_code": "BNP001",
                "date_arrete": "2024-01-31",
                "version_code": "V2024_01",
                "table_name": table,
            },
            files={"file": (f, fh, "text/csv")},
            timeout=120,
        )
    print(f"  -> {r.status_code}: {r.text[:300]}")
    if r.status_code >= 400:
        print(f"  ERREUR!")

print("\nTerminé. Consultez le dashboard pour voir les résultats.")
