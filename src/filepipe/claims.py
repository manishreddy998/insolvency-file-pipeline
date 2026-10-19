"""Claim checker for the trustee note. Every number, date and percent in the note must come from the file's
verified figures, or the sentence is dropped. Loaded words that turn a note into a judgement are dropped too.

This is what lets a small local model write the note without being trusted with facts: the OSB reminds trustees
they are accountable for the accuracy of anything produced with AI.
"""
from __future__ import annotations

import re

MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?%")
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
NUMBER = re.compile(r"(?<![\w.$])(\d[\d,]*(?:\.\d+)?)(?![\w%])")
LOADED = re.compile(r"\b(fraud\w*|lie[sd]?|lying|hid(?:e|den|ing)|dishonest\w*|suspicious|likely|probably|"
                    r"approximately|roughly|about|estimated|guarantee\w*|will be approved|must be rejected)\b", re.I)


def _f(s: str) -> float:
    return float(s.replace(",", ""))


def claims(text: str) -> list[dict]:
    out, t = [], text
    for m in DATE.finditer(t):
        out.append({"kind": "date", "raw": m.group(0), "value": m.group(1)})
    t = DATE.sub(" ", t)
    for m in MONEY.finditer(t):
        out.append({"kind": "money", "raw": m.group(0), "value": _f(m.group(1))})
    t = MONEY.sub(" ", t)
    for m in PERCENT.finditer(t):
        out.append({"kind": "percent", "raw": m.group(0), "value": _f(m.group(1))})
    t = PERCENT.sub(" ", t)
    for m in NUMBER.finditer(t):
        out.append({"kind": "number", "raw": m.group(0), "value": _f(m.group(1))})
    return out


def unsupported(sentence: str, numbers: set, dates: set) -> list[dict]:
    bad = [{"kind": "word", "raw": m.group(0)} for m in LOADED.finditer(sentence)]
    for c in claims(sentence):
        if c["kind"] == "date":
            ok = c["value"] in dates
        else:
            ok = any(abs(c["value"] - n) < 0.005 for n in numbers)
        if not ok:
            bad.append(c)
    return bad


def allowed(facts: dict) -> tuple[set, set]:
    nums, dates = set(), set()

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            nums.add(float(x))
        elif isinstance(x, str):
            if DATE.fullmatch(x):
                dates.add(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
    walk(facts)
    nums.update({0.0, 1.0, 2.0, 3.0, 50.0, 200.0})  # rule constants a note may quote
    return nums, dates


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def check_note(note: str, facts: dict) -> dict:
    nums, dates = allowed(facts)
    kept, dropped = [], []
    for s in split_sentences(note):
        bad = unsupported(s, nums, dates)
        (dropped if bad else kept).append({"sentence": s, "unsupported": bad})
    return {"kept": [k["sentence"] for k in kept], "dropped": dropped}
