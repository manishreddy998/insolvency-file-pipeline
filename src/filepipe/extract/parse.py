"""Small parsers for money, dates and names that survive common OCR mistakes."""
from __future__ import annotations

import re
from datetime import date, datetime

from rapidfuzz import fuzz

# characters Tesseract often swaps for digits inside amounts
DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "S": "5", "s": "5", "l": "1", "I": "1",
                           "|": "1", "i": "1", "B": "8", "Z": "2", "z": "2", "g": "9"})
# the first character must be a real digit (or follow a $), so a word like "CHAVEZ 859.20" stays 859.20
MONEY = re.compile(r"(?:(?<=\$)|(?<![A-Za-z0-9]))\s?([0-9][0-9OoDQSslI|iBZzg,]{0,10}(?:\s[0-9]{3})?[.,]\s?[0-9OoSslI|BZzg]{2})(?![0-9])")
STRICT_MONEY = re.compile(r"\$?\s?(\d{1,3}(?:,\d{3})*\.\d{2})(?!\d)")


def parse_money(text: str, repair: bool = True) -> float | None:
    """Last amount on the line. With repair off, only a clean 1,234.56 style amount counts."""
    if not repair:
        m = STRICT_MONEY.findall(text)
        return float(m[-1].replace(",", "")) if m else None
    hits = MONEY.findall(text)
    if not hits:
        return None
    raw = hits[-1].translate(DIGIT_FIX).replace(" ", "")
    # a comma before the last two digits is a misread decimal point
    if re.search(r",\d{2}$", raw) and "." not in raw:
        raw = raw[:-3] + "." + raw[-2:]
    raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_date(text: str) -> str | None:
    t = text.strip().translate(str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1"}))
    m = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
        return _ok(y, mo, d)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", t)  # dd/mm/yyyy as printed on Canadian forms
    if m:
        d, mo, y = map(int, m.groups())
        return _ok(y, mo, d)
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(20\d{2})", text)
    if m and m.group(1)[:3].lower() in MONTHS:
        return _ok(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    return None


def _ok(y, mo, d):
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


POSTAL = re.compile(r"([A-Z0-9][0-9OIlSB][A-Z0-9])\s?([0-9OIlSB][A-Z0-9][0-9OIlSB])")


def parse_postal(text: str) -> str | None:
    m = POSTAL.search(text.upper())
    if not m:
        return None
    a, b = m.groups()
    to_d = str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8"})
    to_l = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B"})
    fix = a[0].translate(to_l) + a[1].translate(to_d) + a[2].translate(to_l) + " " + \
        b[0].translate(to_d) + b[1].translate(to_l) + b[2].translate(to_d)
    return fix


def parse_int(text: str) -> int | None:
    m = re.search(r"\b(\d{1,2})\b", text.translate(str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1"})))
    return int(m.group(1)) if m else None


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def same_name(a: str, b: str, cut: int = 85) -> bool:
    return fuzz.token_sort_ratio(norm_name(a), norm_name(b)) >= cut


def days_between(a: str, b: str) -> int:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).days
