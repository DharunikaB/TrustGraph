"""Pydantic contracts for the M5 Policy Engine.

DECISION VOCABULARY: `PolicyDecisionType` reuses `app.agent.models.RecommendedAction`
directly rather than defining a parallel enum with the same five values
(`NO_ACTION, MONITOR, REVIEW, HOLD_FOR_REVIEW, ESCALATE`). M4's spec
already required this exact closed vocabulary for AI recommendations;
M5's spec asks for the identical vocabulary for both policy decisions
and the action taxonomy. Rather than three near-identical enums
drifting independently, all three (`InvestigationResult.recommended_action`,
`PolicyDecision.decision`, `ActionRequest.action_type`) are the SAME
Python enum class -- one closed vocabulary, everywhere. M4 is not
modified to achieve this; the enum simply lives where M4 already put
it and is imported here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.agent.models import RecommendedAction as PolicyDecisionType
from app.risk.config import RiskLevel

__all__ = ["PolicyDecisionType", "ReasonCode", "PolicyDecision"]


class ReasonCode(str, Enum):
    """Closed vocabulary of reasons a PolicyDecision can cite.

    Deliberately NOT free-form strings -- every reason a decision can
    carry is one of these, so audit records and tests can reason about
    "why" mechanically rather than parsing prose.
    """

    # Risk-level baseline (exactly one of these four is always present)
    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL_RISK = "CRITICAL_RISK"

    # Financial materiality
    SIGNIFICANT_FINANCIAL_EXPOSURE = "SIGNIFICANT_FINANCIAL_EXPOSURE"

    # AI investigation input (M4)
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONTRADICTING_EVIDENCE_PRESENT = "CONTRADICTING_EVIDENCE_PRESENT"
    LEGITIMATE_SHARED_INFRASTRUCTURE_INDICATED = "LEGITIMATE_SHARED_INFRASTRUCTURE_INDICATED"

    # AI recommendation vs. policy decision relationship (see rules.py)
    AI_RECOMMENDATION_ACCEPTED = "AI_RECOMMENDATION_ACCEPTED"
    AI_ESCALATION_REJECTED_LOW_CONFIDENCE = "AI_ESCALATION_REJECTED_LOW_CONFIDENCE"
    AI_ESCALATION_REJECTED_LEGITIMATE_CLASSIFICATION = "AI_ESCALATION_REJECTED_LEGITIMATE_CLASSIFICATION"
    AI_DEESCALATION_REJECTED = "AI_DEESCALATION_REJECTED"


class PolicyDecision(BaseModel):
    """The deterministic output of PolicyEngine.evaluate().

    `risk_score`/`risk_level` are a READ-ONLY SNAPSHOT of the M3 values
    used to make this decision -- carried here for audit/display
    convenience, never a second source of truth and never mutated by
    anything downstream (see the "M3 values unchanged" tests).
    """

    model_config = ConfigDict(frozen=True)

    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cluster_id: str
    investigation_id: str

    decision: PolicyDecisionType
    reason_codes: list[ReasonCode]
    decision_reason: str = Field(min_length=1)
    policy_version: str
    requires_human_review: bool

    ai_recommendation: PolicyDecisionType | None
    ai_recommendation_followed: bool

    risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
