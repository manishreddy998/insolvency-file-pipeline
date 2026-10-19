"""Trustee fees for a consumer proposal under Rule 129 of the Bankruptcy and Insolvency General Rules.

https://laws-lois.justice.gc.ca/eng/regulations/C.R.C.,_c._368/section-129.html
$750 on filing, $750 on court approval or deemed approval, and 20 per cent of the moneys distributed to creditors.
Counselling (Rule 131, $85 per session), filing fees and taxes are left out on purpose.
A November 2025 Canada Gazette proposal would change this to a maximum, so treat these as today's numbers.
"""

FILING_FEE = 750.0
APPROVAL_FEE = 750.0
DISTRIBUTION_SHARE = 0.20


def proposal_fees(distributed_to_creditors: float, approved: bool = True) -> float:
    """Rule 129(1)(a) to (c). The 20% is on money distributed to creditors, so it only arrives if payments keep coming."""
    base = FILING_FEE + (APPROVAL_FEE if approved else 0.0)
    return round(base + DISTRIBUTION_SHARE * max(distributed_to_creditors, 0.0), 2)


def split_payments(paid_in: float) -> dict:
    """How money paid into a proposal splits when the 20% fee comes out of each distribution.

    If D is distributed and 0.2 D is the fee, then paid_in = 1.2 D. Counselling and filing fees are ignored here.
    """
    d = max(paid_in, 0.0) / (1 + DISTRIBUTION_SHARE)
    return {"distributed": round(d, 2), "distribution_fee": round(d * DISTRIBUTION_SHARE, 2)}
