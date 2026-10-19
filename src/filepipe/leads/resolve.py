"""Identity resolution: which touches are the same person?

Baseline: exact match on the raw email or raw phone text, which is what a simple CRM duplicate rule does.
Resolver: normalised keys, blocking, a name check on shared phones, and union find.
"""
from __future__ import annotations

import itertools
import re
from collections import defaultdict

import pandas as pd
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from filepipe.leads.synth import NICK

NICK_BACK = {v.lower(): k.lower() for k, v in NICK.items()}


def norm_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d if len(d) == 10 else ""


def phone_tail(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    return d[-7:] if len(d) >= 7 else ""


def norm_email(e: str) -> str:
    e = (e or "").strip().lower()
    if "@" not in e:
        return ""
    user, dom = e.split("@", 1)
    user = user.split("+", 1)[0]
    if dom == "gmail.com":
        user = user.replace(".", "")
    return f"{user}@{dom}"


def _first(name: str) -> str:
    f = (name or "").split(" ")[0].lower()
    return NICK_BACK.get(f, f)


def _last(name: str) -> str:
    parts = (name or "").split(" ")
    return parts[-1].lower() if len(parts) > 1 else ""


class UF:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def _names_agree(a: str, b: str, need: int) -> bool:
    fa, fb = _first(a), _first(b)
    if not fa or not fb:
        return True
    first_ok = fuzz.ratio(fa, fb) >= need or (fa[0] == fb[0] and JaroWinkler.similarity(fa, fb) >= 0.88)
    la, lb = _last(a), _last(b)
    last_ok = not la or not lb or fuzz.ratio(la, lb) >= 80
    return first_ok and last_ok


def baseline(t: pd.DataFrame) -> pd.Series:
    uf = UF(t["touch_id"])
    for col in ("email", "phone"):
        for _, g in t[t[col] != ""].groupby(col):
            ids = list(g["touch_id"])
            for x in ids[1:]:
                uf.union(ids[0], x)
    return t["touch_id"].map(uf.find)


def resolve(t: pd.DataFrame) -> pd.Series:
    t = t.assign(e=t["email"].map(norm_email), p=t["phone"].map(norm_phone), p7=t["phone"].map(phone_tail))
    uf = UF(t["touch_id"])
    rec = t.set_index("touch_id")
    # 1) same normalised email: same person
    for _, g in t[t["e"] != ""].groupby("e"):
        ids = list(g["touch_id"])
        for x in ids[1:]:
            uf.union(ids[0], x)
    # 2) same phone (full or last 7 digits): same person only if the first names agree, since a home phone is shared
    for key in ("p", "p7"):
        for _, g in t[t[key] != ""].groupby(key):
            ids = list(g["touch_id"])
            if len(ids) > 30:
                continue
            for a, b in itertools.combinations(ids, 2):
                if _names_agree(rec.at[a, "name"], rec.at[b, "name"], 85):
                    uf.union(a, b)
    # 3) no shared key: very close full name in the same FSA, and no contradicting email
    t["blk"] = t["name"].map(lambda n: _last(n)[:3]) + "|" + t["fsa"]
    for blk, g in t[(t["fsa"] != "") & t["name"].str.contains(" ")].groupby("blk"):
        ids = list(g["touch_id"])
        if len(ids) > 40:
            continue
        for a, b in itertools.combinations(ids, 2):
            ea, eb = rec.at[a, "email"], rec.at[b, "email"]
            if ea and eb and norm_email(ea) != norm_email(eb):
                continue
            pa, pb = phone_tail(rec.at[a, "phone"]), phone_tail(rec.at[b, "phone"])
            if pa and pb and pa != pb:
                continue
            if fuzz.token_sort_ratio(rec.at[a, "name"].lower(), rec.at[b, "name"].lower()) >= 92:
                uf.union(a, b)
    # 4) same full name (nicknames mapped back) with nothing that contradicts it, when that name is rare
    t["full"] = t["name"].map(lambda n: f"{_first(n)} {_last(n)}" if " " in (n or "") else "")
    named = t[t["full"] != ""]
    keys = named.assign(k=named["p7"].where(named["p7"] != "", named["e"])).query("k != ''")
    rare = keys.groupby("full")["k"].nunique()
    rare = set(rare[rare <= 1].index) | (set(named["full"]) - set(keys["full"]))
    for full, g in named[named["full"].isin(rare)].groupby("full"):
        ids = list(g["touch_id"])
        if len(ids) > 12:
            continue
        for a, b in itertools.combinations(ids, 2):
            fa, fb = rec.at[a, "fsa"], rec.at[b, "fsa"]
            if fa and fb and fa != fb:
                continue
            uf.union(a, b)
    return t["touch_id"].map(uf.find)


def pair_scores(truth: pd.Series, pred: pd.Series) -> dict:
    """Pairwise precision and recall: of the touch pairs we joined, how many are truly one person, and the reverse."""
    def pairs(labels: pd.Series) -> set:
        out = set()
        groups = defaultdict(list)
        for idx, lab in labels.items():
            groups[lab].append(idx)
        for ids in groups.values():
            out.update(itertools.combinations(sorted(ids), 2))
        return out
    tp_, pp_ = pairs(truth), pairs(pred)
    tp = len(tp_ & pp_)
    return {"precision": round(tp / max(len(pp_), 1), 4), "recall": round(tp / max(len(tp_), 1), 4),
            "true_pairs": len(tp_), "predicted_pairs": len(pp_),
            "people_true": int(truth.nunique()), "people_found": int(pred.nunique())}
