"""Advertising rules check. Posts that break a rule are never auto-posted: they are held for you to review.

Mortgage: Reg Z / TILA "trigger terms" (a rate, a payment amount, a down-payment amount or number of payments)
require a full APR disclosure, so any post containing one is held. Promise words are held for both businesses.
"""
import re

HOLD = {
    "all": [
        (r"\bguarantee[ds]?\b", "promise word 'guarantee'"),
        (r"\bbest (rate|price|deal)s?\b", "superlative 'best rate/price'"),
        (r"\bbetter (rate|price|deal)s?\b", "comparison claim 'better rate/price'"),
        (r"\b(cheapest|lowest)\b", "superlative 'cheapest/lowest'"),
        (r"\bsave (up to )?\d", "savings claim with a number"),
        (r"\b100\s?%", "100% claim"),
    ],
    "mortgage": [
        (r"\d+(\.\d+)?\s?%", "Reg Z trigger term: a percentage (rate or down payment)"),
        (r"\$\s?\d[\d,]*(\.\d+)?\s*(/|per|a)\s*(mo|month)", "Reg Z trigger term: a payment amount"),
        (r"\b\d+\s*(monthly )?payments\b", "Reg Z trigger term: number of payments"),
        (r"\$\s?0 down|zero down|no money down", "Reg Z trigger term: down payment amount"),
        (r"\bno credit check\b", "'no credit check' claim"),
        (r"\b(everyone|anyone) (is |gets )?(approved|qualifies)\b", "approval promise"),
        (r"\binstant(ly)? approv", "approval promise"),
        (r"\bpre-?approved\b(?! letter| process)", "'pre-approved' wording"),
    ],
    "insurance": [
        (r"\b(fully|always|completely) covered\b", "coverage promise"),
        (r"\bcovers everything\b", "coverage promise"),
        (r"\bno (claim|claims) denied\b", "claims promise"),
    ],
}


def check(text, industry):
    reasons = []
    low = text.lower()
    for pattern, why in HOLD["all"] + HOLD.get(industry, []):
        if re.search(pattern, low):
            reasons.append(why)
    return sorted(set(reasons))


def scrub_for_google(text):
    """Google Business Profile rejects posts that contain phone numbers."""
    return re.sub(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", "", text)
