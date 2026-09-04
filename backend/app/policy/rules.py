"""Pure, deterministic policy rule functions.

Kept separate from `engine.py`'s orchestration so each rule can be
read, tested, and reasoned about independently. Nothing here touches
the database, Gemini, or any I/O -- every function is a plain
computation over already-in-memory M3/M4 values.
"""

from __future__ import annotations

from app.policy.config import PolicyConfig
from app.policy.models import PolicyDecisionType


def severity_index(decision: PolicyDecisionType, config: PolicyConfig) -> int:
    return config.decision_order.index(decision)


def more_severe(a: PolicyDecisionType, b: PolicyDecisionType, config: PolicyConfig) -> bool:
    """True if `a` is strictly more severe than `b`."""
    return severity_index(a, config) > severity_index(b, config)


def escalate_one_step(decision: PolicyDecisionType, config: PolicyConfig) -> PolicyDecisionType:
    """One step more severe, capped at the most severe defined decision."""
    idx = min(len(config.decision_order) - 1, severity_index(decision, config) + 1)
    return config.decision_order[idx]


def baseline_decision(risk_level, config: PolicyConfig) -> PolicyDecisionType:
    """The pure risk-level-driven decision, before exposure/AI adjustments."""
    return config.risk_level_baseline[risk_level]


def apply_exposure_escalation(
    decision: PolicyDecisionType, estimated_exposure: float, config: PolicyConfig
) -> tuple[PolicyDecisionType, bool]:
    """Bump one step if financial exposure is significant. Returns (decision, was_escalated)."""
    if estimated_exposure >= config.high_exposure_threshold:
        return escalate_one_step(decision, config), True
    return decision, False


def resolve_ai_recommendation(
    current_decision: PolicyDecisionType,
    ai_recommendation: PolicyDecisionType,
    ai_confidence: float,
    is_legitimate_classification: bool,
    config: PolicyConfig,
) -> tuple[PolicyDecisionType, str]:
    """Reconcile the AI's recommendation against the current (risk+exposure)
    decision. Returns (final_decision, reason_code_name).

    THE CORE M5 PRINCIPLE, encoded here:

    - AI can push the decision MORE severe, but only when it is
      reasonably confident (>= min_confidence_for_ai_escalation) AND
      its own classification doesn't already read as legitimate shared
      infrastructure (an AI that says "this looks legitimate" but also
      recommends ESCALATE is internally inconsistent -- policy doesn't
      reward that).
    - AI can NEVER pull the decision below what risk+exposure already
      established. Per the spec's explicit example: Gemini recommending
      NO_ACTION while deterministic conditions are severe must NOT
      de-escalate anything -- the deterministic floor always holds.
    - Equal severity is trivially "accepted" (nothing to override).
    """
    if ai_recommendation == current_decision:
        return current_decision, "AI_RECOMMENDATION_ACCEPTED"

    if more_severe(ai_recommendation, current_decision, config):
        if is_legitimate_classification:
            return current_decision, "AI_ESCALATION_REJECTED_LEGITIMATE_CLASSIFICATION"
        if ai_confidence < config.min_confidence_for_ai_escalation:
            return current_decision, "AI_ESCALATION_REJECTED_LOW_CONFIDENCE"
        return ai_recommendation, "AI_RECOMMENDATION_ACCEPTED"

    # ai_recommendation is LESS severe than current_decision -- rejected,
    # unconditionally, regardless of confidence.
    return current_decision, "AI_DEESCALATION_REJECTED"


def requires_human_review(decision: PolicyDecisionType, config: PolicyConfig) -> bool:
    return decision in config.human_review_decisions
