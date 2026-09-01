"""
Kyro Discord Bot - Centralized Pricing & Plans Configuration
Defines pricing tiers, durations, dual-currency amounts in USD ($) & INR (₹), and smallest unit charges.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class PlanDefinition:
    plan_id: str
    name: str
    duration_days: int             # 0 = Lifetime
    amount_usd: float              # Display amount in USD ($)
    amount_inr: int                # Display amount in INR (₹)
    amount_smallest_unit: int      # Amount in smallest currency unit (paise for INR, cents for USD)
    currency: str                  # Base settlement currency ('INR')
    target_type: str               # 'guild' or 'user'
    description: str
    is_trial: bool = False


# Server Pro Tier Plans (Dual Currency $USD & ₹INR)
SERVER_PLANS: dict[str, PlanDefinition] = {
    "trial_3d": PlanDefinition(
        plan_id="trial_3d",
        name="3-Day Free Trial",
        duration_days=3,
        amount_usd=0.00,
        amount_inr=0,
        amount_smallest_unit=0,
        currency="INR",
        target_type="guild",
        description="Full access to all Pro features for 3 days (1-time offer).",
        is_trial=True,
    ),
    "1_month": PlanDefinition(
        plan_id="1_month",
        name="1 Month Pro",
        duration_days=30,
        amount_usd=4.99,
        amount_inr=399,
        amount_smallest_unit=39900,
        currency="INR",
        target_type="guild",
        description="Recommended starting plan for active community servers.",
    ),
    "3_months": PlanDefinition(
        plan_id="3_months",
        name="3 Months Pro",
        duration_days=90,
        amount_usd=11.99,
        amount_inr=999,
        amount_smallest_unit=99900,
        currency="INR",
        target_type="guild",
        description="Quarterly package with built-in discount.",
    ),
    "1_year": PlanDefinition(
        plan_id="1_year",
        name="1 Year Pro",
        duration_days=365,
        amount_usd=39.99,
        amount_inr=3299,
        amount_smallest_unit=329900,
        currency="INR",
        target_type="guild",
        description="Best value enterprise package for growing communities.",
    ),
    "lifetime": PlanDefinition(
        plan_id="lifetime",
        name="Lifetime Pro",
        duration_days=0,
        amount_usd=69.99,
        amount_inr=5799,
        amount_smallest_unit=579900,
        currency="INR",
        target_type="guild",
        description="Permanent VIP superpower access with zero recurring fees.",
    ),
}


def get_plan(plan_id: str) -> PlanDefinition | None:
    """Retrieve plan definition by ID."""
    return SERVER_PLANS.get(plan_id)
