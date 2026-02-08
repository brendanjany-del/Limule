"""Upload les fichiers d'exemple via l'API locale.

Usage:
  python scripts/upload_samples.py                  # petits fichiers ETB001
  python scripts/upload_samples.py --large           # gros fichiers CELC (1M+ lignes)
"""
import httpx
import os
import sys
import time

BASE = "http://localhost:8000"

SMALL_FILES = [
    ("tiers", "V2024_01_ETB001_202401_tiers.csv", "ETB001", "2024-01-31"),
    ("contrats", "V2024_01_ETB001_202401_contrat.csv", "ETB001", "2024-01-31"),
    ("titres", "V2024_01_ETB001_202401_titre.csv", "ETB001", "2024-01-31"),
    ("liens", "V2024_01_ETB001_202401_lien.csv", "ETB001", "2024-01-31"),
]

LARGE_FILES = [
    ("tiers", "V2024_01_CELC_202512_tiers.csv", "CELC", "2025-12-31"),
    ("contrats", "V2024_01_CELC_202512_contrat.csv", "CELC", "2025-12-31"),
    ("titres", "V2024_01_CELC_202512_titre.csv", "CELC", "2025-12-31"),
    ("liens", "V2024_01_CELC_202512_lien.csv", "CELC", "2025-12-31"),
]

data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "input")

use_large = "--large" in sys.argv
files = LARGE_FILES if use_large else SMALL_FILES
timeout = 600 if use_large else 120

print(f"Mode: {'LARGE (CELC 2025-12)' if use_large else 'SMALL (ETB001 2024-01)'}\n")

for table, f, etb, arrete in files:
    path = os.path.join(data_dir, f)
    if not os.path.exists(path):
        print(f"FICHIER MANQUANT: {path}")
        continue

    size_mb = os.path.getsize(path) / 1024 / 1024
    print(f"Upload {table} ({f}, {size_mb:.1f} MB)...")
    t0 = time.time()

    with open(path, "rb") as fh:
        r = httpx.post(
            f"{BASE}/api/flux/upload",
            data={
                "etablissement_code": etb,
                "date_arrete": arrete,
                "version_code": "V2024_01",
                "table_name": table,
            },
            files={"file": (f, fh, "text/csv")},
            timeout=timeout,
        )

    elapsed = time.time() - t0
    print(f"  -> {r.status_code} ({elapsed:.1f}s): {r.text[:300]}")
    if r.status_code >= 400:
        print(f"  ERREUR!")

print("\nTerminé. Consultez le dashboard pour voir les résultats.")
