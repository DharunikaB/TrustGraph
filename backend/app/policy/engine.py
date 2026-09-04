"""The deterministic Policy Engine.

    ScoredCluster (M3)  +  InvestigationResult (M4)
                    |
                    v
            baseline_decision           (risk level only)
                    |
                    v
        apply_exposure_escalation        (financial materiality)
                    |
                    v
        resolve_ai_recommendation         (AI as INPUT, never final)
                    |
                    v
             PolicyDecision

`evaluate()` is a pure function of its two inputs -- same
(ScoredCluster, InvestigationResult) always produces the same decision
(modulo `decision_id`/`generated_at`, which are identity/timestamp
fields, not decision content). It never touches the database, Gemini,
or ground truth.
"""

from __future__ import annotations

from app.agent.models import Classification, InvestigationResult, InvestigationStatus
from app.policy.config import PolicyConfig
from app.policy.models import PolicyDecision, ReasonCode
from app.policy.rules import (
    apply_exposure_escalation,
    baseline_decision,
    requires_human_review,
    resolve_ai_recommendation,
)
from app.risk.models import ScoredCluster

_RISK_LEVEL_REASON = {
    "LOW": ReasonCode.LOW_RISK,
    "MEDIUM": ReasonCode.MEDIUM_RISK,
    "HIGH": ReasonCode.HIGH_RISK,
    "CRITICAL": ReasonCode.CRITICAL_RISK,
}


class PolicyEngine:
    def __init__(self, config: PolicyConfig | None = None):
        self.config = config or PolicyConfig()

    def evaluate(self, cluster: ScoredCluster, investigation: InvestigationResult) -> PolicyDecision:
        reason_codes: list[ReasonCode] = [_RISK_LEVEL_REASON[cluster.risk.level.value]]

        decision = baseline_decision(cluster.risk.level, self.config)

        decision, exposure_escalated = apply_exposure_escalation(
            decision, cluster.exposure.estimated_exposure, self.config
        )
        if exposure_escalated:
            reason_codes.append(ReasonCode.SIGNIFICANT_FINANCIAL_EXPOSURE)

        ai_recommendation = None
        ai_followed = False

        if investigation.status == InvestigationStatus.COMPLETED and investigation.assessment is not None:
            classification = investigation.assessment.classification
            confidence = investigation.assessment.confidence
            ai_recommendation = investigation.recommended_action

            if classification == Classification.INSUFFICIENT_EVIDENCE:
                reason_codes.append(ReasonCode.INSUFFICIENT_EVIDENCE)
            if investigation.contradicting_evidence:
                reason_codes.append(ReasonCode.CONTRADICTING_EVIDENCE_PRESENT)
            if classification == Classification.LEGITIMATE_SHARED_INFRASTRUCTURE:
                reason_codes.append(ReasonCode.LEGITIMATE_SHARED_INFRASTRUCTURE_INDICATED)

            decision, reason_name = resolve_ai_recommendation(
                current_decision=decision,
                ai_recommendation=ai_recommendation,
                ai_confidence=confidence,
                is_legitimate_classification=(classification == Classification.LEGITIMATE_SHARED_INFRASTRUCTURE),
                config=self.config,
            )
            reason_codes.append(ReasonCode[reason_name])
            ai_followed = decision == ai_recommendation
        else:
            # Covers BOTH InvestigationStatus.AI_UNAVAILABLE (provider/
            # connectivity failure) and INVESTIGATION_FAILED (validation
            # failure) -- from the Policy Engine's perspective both mean
            # "no usable AI recommendation was available", and the
            # deterministic risk+exposure baseline is used unchanged
            # either way. The distinction between the two is preserved
            # in `investigation.status` itself (and in M4's own audit
            # logging) for anyone who needs it.
            reason_codes.append(ReasonCode.AI_UNAVAILABLE)

        human_review = requires_human_review(decision, self.config) or (
            investigation.status == InvestigationStatus.COMPLETED
            and investigation.assessment is not None
            and investigation.assessment.classification == Classification.INSUFFICIENT_EVIDENCE
        )

        return PolicyDecision(
            cluster_id=cluster.cluster_id,
            investigation_id=investigation.investigation_id,
            decision=decision,
            reason_codes=reason_codes,
            decision_reason=_build_decision_reason(cluster, investigation, decision, reason_codes),
            policy_version=self.config.policy_version,
            requires_human_review=human_review,
            ai_recommendation=ai_recommendation,
            ai_recommendation_followed=ai_followed,
            risk_score=cluster.risk.score,
            risk_level=cluster.risk.level,
        )


def _build_decision_reason(
    cluster: ScoredCluster,
    investigation: InvestigationResult,
    decision,
    reason_codes: list[ReasonCode],
) -> str:
    parts = [
        f"M3 risk level {cluster.risk.level.value} (score {cluster.risk.score})",
    ]
    if ReasonCode.SIGNIFICANT_FINANCIAL_EXPOSURE in reason_codes:
        parts.append(f"significant financial exposure (Rs {cluster.exposure.estimated_exposure:,.2f})")
    if investigation.status == InvestigationStatus.COMPLETED and investigation.assessment is not None:
        parts.append(
            f"AI classification {investigation.assessment.classification.value} "
            f"(confidence {investigation.assessment.confidence})"
        )
    else:
        parts.append(f"AI investigation unavailable (status {investigation.status.value})")
    return f"Decision {decision.value} based on: " + "; ".join(parts) + "."


# ----------------------------------------------------------------------
# In-memory decision store -- supports GET /policy/decisions/{decision_id}.
#
# Deliberately NOT a database table for M5: PolicyDecision is already a
# frozen Pydantic snapshot, and adding persistence now would be the
# same kind of unnecessary infrastructure M4 avoided for
# InvestigationResult. A future milestone can back this with a real
# table without changing PolicyDecision's shape at all.
# ----------------------------------------------------------------------
class PolicyDecisionStore:
    def __init__(self):
        self._decisions: dict[str, PolicyDecision] = {}

    def save(self, decision: PolicyDecision) -> None:
        self._decisions[decision.decision_id] = decision

    def get(self, decision_id: str) -> PolicyDecision | None:
        return self._decisions.get(decision_id)

    def clear(self) -> None:
        self._decisions.clear()


policy_decision_store = PolicyDecisionStore()
