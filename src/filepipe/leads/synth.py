"""Synthetic leads for the lead to completed view. Every person and touch here is fictional.

One person can reach out more than once and on more than one channel (chat, call, web form). The same person
looks a little different each time: a nickname, a typo, a phone typed with or without the area code, an email
with capitals or dots. Two people in one household can share a phone. The answer key (person_id) is kept so
identity resolution can be scored.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd
from faker import Faker

CHANNELS = ["chat", "call", "form"]
# synthetic media cost per raw touch, by channel; stated as made up in the README
COST_PER_TOUCH = {"chat": 38.0, "call": 95.0, "form": 60.0}
NICK = {"Robert": "Rob", "William": "Bill", "Elizabeth": "Liz", "Jennifer": "Jen", "Michael": "Mike",
        "Christopher": "Chris", "Katherine": "Kate", "Matthew": "Matt", "Daniel": "Dan", "Jessica": "Jess",
        "Joseph": "Joe", "Anthony": "Tony", "Patricia": "Pat", "Stephanie": "Steph", "Samantha": "Sam"}
STAGE_P = {  # consult given lead, signed given consult; filed is the ledger
    "chat": (0.45, 0.55), "call": (0.70, 0.65), "form": (0.55, 0.60)}


def _typo(s: str, rng: random.Random) -> str:
    if len(s) < 4:
        return s
    i = rng.randint(1, len(s) - 2)
    op = rng.choice(["swap", "drop", "double"])
    if op == "swap":
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if op == "drop":
        return s[:i] + s[i + 1:]
    return s[:i] + s[i] + s[i:]


def _phone_variant(p: str, rng: random.Random) -> str:
    d = p
    return rng.choice([f"({d[:3]}) {d[3:6]}-{d[6:]}", f"{d[:3]}-{d[3:6]}-{d[6:]}", d, f"+1 {d[:3]} {d[3:6]} {d[6:]}",
                       f"1{d}", f"{d[3:6]}-{d[6:]}"])  # the last one drops the area code


def _email_variant(e: str, rng: random.Random) -> str:
    user, dom = e.split("@")
    r = rng.random()
    if r < 0.2:
        return e.upper() if rng.random() < 0.3 else user.capitalize() + "@" + dom
    if r < 0.3 and dom == "gmail.com" and len(user) > 4:
        return user[:3] + "." + user[3:] + "@" + dom
    if r < 0.35:
        return user + "+farber@" + dom
    return e


def simulate_leads(files: pd.DataFrame, extra_people: int = 9000, seed: int = 21) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (people, touches). people has the truth: channel of first touch, stages, ledger file_id."""
    rng = random.Random(seed)
    fk = Faker("en_CA")
    fk.seed_instance(seed)
    people, touches = [], []
    fsas = ["M1B", "L5B", "L4N", "K1S", "N6A", "L8W", "M9B", "T5J", "V3H", "B3J", "L7A", "L6Y", "K0K", "T5T"]
    filed = files.sort_values("start").to_dict("records")
    n = len(filed) + extra_people
    households = {}
    for i in range(n):
        f = filed[i] if i < len(filed) else None
        if f is not None:
            start = date.fromisoformat(f["start"])
            w = [0.40 + 0.08 * f["intake_flags"], 0.35, 0.25]
        else:
            start = date(2021, 1, 1) + timedelta(days=rng.randint(0, 2060))
            w = [0.52, 0.22, 0.26]
        ch = rng.choices(CHANNELS, w)[0]
        first, last = fk.first_name(), fk.last_name()
        hh = None
        if i > 50 and rng.random() < 0.04:  # spouse or adult child of an earlier lead, same home phone
            hh = rng.choice(list(households))
            last = households[hh]["last"]
        phone = households[hh]["phone"] if hh is not None else fk.numerify("%##%######")
        email = f"{first.lower()}.{last.lower()}{rng.randint(1, 99)}@{rng.choice(['gmail.com', 'outlook.com', 'yahoo.ca', 'rogers.com'])}"
        email = email.replace(" ", "").replace("'", "")
        pid = f"PER{i:05d}"
        households.setdefault(pid if hh is None else hh, {"last": last, "phone": phone})
        if f is not None:
            consult = signed = True
        else:
            pc, ps = STAGE_P[ch]
            consult = rng.random() < pc
            signed = consult and rng.random() < ps * 0.35  # signed but not yet filed, or chose another path
        fsa = rng.choice(fsas)
        people.append({"person_id": pid, "first_channel": ch, "first": first, "last": last, "phone": phone,
                       "email": email, "fsa": fsa, "consult": int(consult), "signed": int(signed),
                       "filed": int(f is not None), "file_id": f["file_id"] if f else None,
                       "outcome": f["outcome"] if f else None, "household_of": hh})
        k = rng.choices([1, 2, 3, 4], [0.52, 0.28, 0.13, 0.07])[0]
        t0 = start - timedelta(days=rng.randint(10, 75))
        for j in range(k):
            c = ch if j == 0 else rng.choices(CHANNELS, [0.35, 0.40, 0.25])[0]
            fn = first
            if rng.random() < 0.15:
                fn = NICK.get(first, first)
            if rng.random() < 0.08:
                fn = _typo(fn, rng)
            ln = _typo(last, rng) if rng.random() < 0.08 else last
            has_phone = c == "call" or rng.random() < (0.55 if c == "chat" else 0.9)
            has_email = c != "call" and rng.random() < (0.6 if c == "chat" else 0.95)
            touches.append({"touch_id": f"T{len(touches):06d}", "person_id": pid, "channel": c,
                            "ts": (t0 + timedelta(days=j * rng.randint(1, 12), minutes=rng.randint(0, 1439))).isoformat(),
                            "name": f"{fn} {ln}" if c != "chat" or rng.random() < 0.7 else fn,
                            "phone": _phone_variant(phone, rng) if has_phone else "",
                            "email": _email_variant(email, rng) if has_email else "",
                            "fsa": fsa if rng.random() < 0.6 else ""})
    return pd.DataFrame(people), pd.DataFrame(touches)
