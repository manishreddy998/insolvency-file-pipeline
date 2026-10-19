"""Download the OSB monthly FSA workbooks (Open Government Licence, Canada).

Dataset page: https://open.canada.ca/data/en/dataset/34e547e9-8e2f-472c-829b-c3c9d2396555
Files already on disk are kept. Run: python -m filepipe.fetch_osb
"""
from __future__ import annotations

import hashlib
import sys

import requests

from filepipe.config import RAW

BASE = "https://ised-isde.canada.ca/site/office-superintendent-bankruptcy/sites/default/files"
FILES = {
    "FSA_RTA_Monthly-Mensuel_2022.xlsx": f"{BASE}/attachments/2023/FSA_RTA_Monthly-Mensuel_2022.xlsx",
    "fsa_rta_monthly_mensuel_2023_dec_2023.xlsx": f"{BASE}/documents/fsa_rta_monthly_mensuel_2023_dec_2023.xlsx",
    "fsa_rta_monthly_mensuel_december-2024.xlsx": f"{BASE}/documents/fsa_rta_monthly_mensuel_december-2024.xlsx",
    "fsa_rta_monthly_mensuel_dec_2025.xlsx": f"{BASE}/documents/fsa_rta_monthly_mensuel_dec_2025.xlsx",
    "fsa_rta_monthly_mensuel_august_2026.xlsx": f"{BASE}/documents/fsa_rta_monthly_mensuel_august_2026.xlsx",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) insolvency-file-pipeline/0.1"}


def fetch(force: bool = False) -> dict:
    out = RAW / "osb"
    out.mkdir(parents=True, exist_ok=True)
    got = {}
    for name, url in FILES.items():
        p = out / name
        if force or not p.exists():
            r = requests.get(url, headers=HEADERS, timeout=120)
            r.raise_for_status()
            p.write_bytes(r.content)
        got[name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return got


if __name__ == "__main__":
    print(fetch(force="--force" in sys.argv))
