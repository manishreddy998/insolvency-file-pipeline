"""A short note for the trustee on each file, written by a small local model and then checked.

The model only rephrases verified figures. The claim checker removes any sentence with a number, date or
loaded word that the figures do not back. If nothing survives, a plain template note is used.
"""
from __future__ import annotations

import json
import time

import requests

from filepipe.claims import check_note
from filepipe.config import llm_model, llm_url

PROMPT = """You write a short note for a Licensed Insolvency Trustee about a client file.
Use only the facts in the JSON. Copy numbers exactly as written, with a dollar sign for money.
Write at most three plain sentences. Do not guess, do not judge the client, do not add any number that is not in the JSON.
Facts: {facts}
Note:"""


def facts_for(res) -> dict:
    s = res.surplus or {}
    return {
        "persons_in_family_unit": res.figures["persons"],
        "client_monthly_net_income": res.figures["debtor_monthly"],
        "family_available_monthly_income": s.get("line8_family_available"),
        "superintendent_standard": s.get("standard"),
        "monthly_surplus_income_payment": s.get("line15_monthly_payment"),
        "unsecured_debt_total": res.figures["unsecured_total"],
        "creditor_count": len(res.creditors),
        "checks_to_review": [f["code"] for f in res.findings if f["severity"] == "check"],
    }


def template_note(f: dict) -> str:
    pay = f["monthly_surplus_income_payment"] or 0
    first = (f"Surplus income payment is ${pay:,.2f} a month." if pay
             else "No surplus income payment is required.")
    checks = ", ".join(c.replace("_", " ") for c in f["checks_to_review"]) or "none"
    return (f"Family unit of {f['persons_in_family_unit']} with client net income of ${f['client_monthly_net_income']:,.2f} a month. "
            f"{first} Unsecured debt is ${f['unsecured_debt_total']:,.2f} across {f['creditor_count']} creditors. "
            f"Checks to review: {checks}.")


class LocalModel:
    name = "local-model"

    def __init__(self):
        self.url, self.model, self.calls, self.seconds = llm_url(), llm_model(), 0, 0.0

    def available(self) -> bool:
        if not self.url:
            return False
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=3)
            return any(m["name"].startswith(self.model) for m in r.json().get("models", []))
        except Exception:
            return False

    def write(self, facts: dict) -> str:
        t = time.time()
        r = requests.post(f"{self.url}/api/generate", timeout=180, json={
            "model": self.model, "prompt": PROMPT.format(facts=json.dumps(facts)), "stream": False,
            "options": {"temperature": 0.1, "num_predict": 110, "seed": 17}})
        r.raise_for_status()
        self.calls += 1
        self.seconds += time.time() - t
        return r.json().get("response", "").strip()


class HostileWriter:
    """Test double that always invents facts. The checker must remove every one of them."""
    name = "hostile"
    calls, seconds = 0, 0.0

    def available(self) -> bool:
        return True

    def write(self, facts: dict) -> str:
        self.calls += 1
        return ("The client probably hid income. Income rose 37% since 2025-01-01. "
                f"Unsecured debt is ${facts['unsecured_debt_total']:,.2f}. They owe $12,345.67 more than listed.")


def note_for(res, writer=None) -> dict:
    f = facts_for(res)
    if writer is None:
        return {"note": template_note(f), "writer": "template", "dropped": [], "facts": f}
    raw = writer.write(f)
    chk = check_note(raw, f)
    note = " ".join(chk["kept"]) if chk["kept"] else template_note(f)
    return {"note": note, "raw": raw, "writer": writer.name, "dropped": chk["dropped"],
            "fell_back": not chk["kept"], "facts": f}


def get_writer(mode: str):
    if mode == "hostile":
        return HostileWriter()
    if mode == "model":
        m = LocalModel()
        return m if m.available() else None
    return None
