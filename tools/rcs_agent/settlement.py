"""Simulated settlement / payment estimator for ClaimPilot (demo).

Produces a plausible repair estimate, deductible, and payout from the damage
description. Deterministic per claim number so the same claim always shows the
same numbers. NOT a real actuarial calculation — demo only.
"""
from __future__ import annotations

import hashlib
from typing import Any

# rough severity → repair band (USD)
_SEVERITY_BANDS = {
    "severe": (6000, 14000),
    "moderate": (2000, 6000),
    "minor": (500, 2000),
}


def _severity(damage_text: str) -> str:
    t = (damage_text or "").lower()
    if any(w in t for w in ("severe", "totaled", "crushed", "structural", "airbag", "undrivable")):
        return "severe"
    if any(w in t for w in ("minor", "scratch", "scuff", "small dent", "cosmetic")):
        return "minor"
    return "moderate"


def estimate(claim_number: str, slots: dict[str, Any], deductible: int = 500) -> dict:
    sev = _severity(slots.get("damage", ""))
    lo, hi = _SEVERITY_BANDS[sev]
    # deterministic pick within the band from the claim number
    h = int(hashlib.sha256(claim_number.encode()).hexdigest(), 16)
    est = lo + (h % (hi - lo + 1))
    est = round(est / 50) * 50  # tidy to $50
    payout = max(0, est - deductible)
    return {
        "severity": sev,
        "estimate": est,
        "deductible": deductible,
        "payout": payout,
    }


def summary_line(settlement: dict) -> str:
    return (f"Estimated payout ${settlement['payout']:,} "
            f"(repair ${settlement['estimate']:,} − ${settlement['deductible']:,} deductible, "
            f"{settlement['severity']}). Pending adjuster review.")
