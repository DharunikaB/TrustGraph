"""Configuration for the M5 Policy Engine.

Every threshold here was chosen by inspecting the actual M3 output
distribution on the verified 1000-customer / 80-cluster dataset (see
the M5 README section), the same evidence-based approach used for
M3's own weights/bands -- not arbitrary round numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.policy.models import PolicyDecisionType
from app.risk.config import RiskLevel


@dataclass
class PolicyConfig:
    policy_version: str = "v1"

    # Deterministic baseline decision by M3 risk level -- this is the
    # policy's starting point BEFORE any AI input is considered, so a
    # cluster with zero/failed AI investigation still gets a sound,
    # risk-driven decision (see PART 5 / human-review boundary below).
    risk_level_baseline: dict[RiskLevel, PolicyDecisionType] = field(
        default_factory=lambda: {
            RiskLevel.LOW: PolicyDecisionType.NO_ACTION,
            RiskLevel.MEDIUM: PolicyDecisionType.MONITOR,
            RiskLevel.HIGH: PolicyDecisionType.HOLD_FOR_REVIEW,
            RiskLevel.CRITICAL: PolicyDecisionType.ESCALATE,
        }
    )

    # Ordinal severity ordering used for escalate/de-escalate comparisons.
    decision_order: tuple[PolicyDecisionType, ...] = (
        PolicyDecisionType.NO_ACTION,
        PolicyDecisionType.MONITOR,
        PolicyDecisionType.REVIEW,
        PolicyDecisionType.HOLD_FOR_REVIEW,
        PolicyDecisionType.ESCALATE,
    )

    # Financial materiality escalation: a cluster whose estimated
    # exposure (M3's returned_value -- see app/risk/models.py's
    # terminology docstring) meets this threshold gets bumped one step
    # more severe than its risk-level baseline, regardless of AI input.
    # Chosen just above the 90th percentile of estimated_exposure
    # (Rs 12,445) across the verified 80-cluster dataset, so only the
    # most financially material ~10% of clusters trigger this.
    high_exposure_threshold: float = 15000.0

    # AI escalation deference: the Policy Engine will adopt a MORE
    # SEVERE AI recommendation than the current (risk+exposure) decision
    # ONLY when Gemini's own confidence in its classification meets this
    # bar AND the classification isn't LEGITIMATE_SHARED_INFRASTRUCTURE.
    # There is no corresponding de-escalation threshold: per the spec's
    # explicit example (Gemini says NO_ACTION but deterministic evidence
    # is severe), AI can NEVER pull a decision below the risk+exposure
    # baseline, at any confidence level -- see rules.py.
    min_confidence_for_ai_escalation: float = 0.6

    # Decisions requiring a human before any further step -- exactly
    # the two "someone must look at this" categories. Chosen to match
    # PART 5 of the spec directly: HIGH -> hold for review (human),
    # CRITICAL -> escalate (human); LOW/MEDIUM's baselines
    # (NO_ACTION/MONITOR) never require one on their own.
    human_review_decisions: tuple[PolicyDecisionType, ...] = (
        PolicyDecisionType.HOLD_FOR_REVIEW,
        PolicyDecisionType.ESCALATE,
    )
