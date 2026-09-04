"""Tests for the M5 Policy Engine: risk-level baselines, exposure
escalation, AI-recommendation reconciliation, determinism, and the
core "AI recommends, policy decides" principle.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.agent.models import (
    Assessment,
    Classification,
    InvestigationMetadata,
    InvestigationResult,
    InvestigationStatus,
    RecommendedAction,
    Severity,
)
from app.policy.config import PolicyConfig
from app.policy.engine import PolicyEngine
from app.policy.models import PolicyDecisionType, ReasonCode
from app.risk.config import RiskLevel
from app.risk.models import Contributor, ExposureAssessment, RiskAssessment, ScoredCluster


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _scored_cluster(risk_level: RiskLevel, risk_score: float, estimated_exposure: float = 0.0) -> ScoredCluster:
    return ScoredCluster(
        cluster_id="cc-test",
        customers=["c1", "c2"],
        devices=["d1"],
        networks=["n1"],
        transactions=["t1"],
        risk=RiskAssessment(
            score=risk_score,
            level=risk_level,
            contributors=[Contributor(signal="test", contribution=risk_score, max_contribution=100, evidence="test")],
        ),
        exposure=ExposureAssessment(
            transaction_count=5, transaction_value=10000.0, order_count=5,
            return_count=1, returned_value=estimated_exposure, estimated_exposure=estimated_exposure,
        ),
        signals={},
        evidence=[],
    )


def _investigation(
    status: InvestigationStatus = InvestigationStatus.COMPLETED,
    classification: Classification = Classification.NORMAL_ACTIVITY,
    confidence: float = 0.8,
    recommended_action: RecommendedAction | None = RecommendedAction.NO_ACTION,
    contradicting_evidence: list[str] | None = None,
) -> InvestigationResult:
    assessment = None
    if status == InvestigationStatus.COMPLETED:
        assessment = Assessment(classification=classification, severity=Severity.LOW, confidence=confidence)
    return InvestigationResult(
        cluster_id="cc-test",
        status=status,
        assessment=assessment,
        summary="test summary" if assessment else None,
        contradicting_evidence=contradicting_evidence or [],
        recommended_action=recommended_action if status == InvestigationStatus.COMPLETED else None,
        metadata=InvestigationMetadata(model="test-model", latency_ms=1.0),
    )


# ----------------------------------------------------------------------
# 1-4: Risk-level baseline behavior
# ----------------------------------------------------------------------
def test_low_risk_produces_safe_policy():
    cluster = _scored_cluster(RiskLevel.LOW, 10.0)
    investigation = _investigation(recommended_action=RecommendedAction.NO_ACTION)
    decision = PolicyEngine().evaluate(cluster, investigation)
    assert decision.decision == PolicyDecisionType.NO_ACTION
    assert decision.requires_human_review is False
    assert ReasonCode.LOW_RISK in decision.reason_codes


def test_medium_risk_produces_review_behavior():
    cluster = _scored_cluster(RiskLevel.MEDIUM, 35.0)
    investigation = _investigation(recommended_action=RecommendedAction.MONITOR)
    decision = PolicyEngine().evaluate(cluster, investigation)
    assert decision.decision == PolicyDecisionType.MONITOR
    assert decision.requires_human_review is False


def test_high_risk_produces_hold_for_review():
    cluster = _scored_cluster(RiskLevel.HIGH, 55.0)
    investigation = _investigation(recommended_action=RecommendedAction.HOLD_FOR_REVIEW)
    decision = PolicyEngine().evaluate(cluster, investigation)
    assert decision.decision == PolicyDecisionType.HOLD_FOR_REVIEW
    assert decision.requires_human_review is True


def test_critical_risk_produces_strongest_response():
    cluster = _scored_cluster(RiskLevel.CRITICAL, 90.0)
    investigation = _investigation(
        classification=Classification.POTENTIAL_COORDINATED_ABUSE,
        recommended_action=RecommendedAction.ESCALATE,
        confidence=0.9,
    )
    decision = PolicyEngine().evaluate(cluster, investigation)
    assert decision.decision == PolicyDecisionType.ESCALATE
    assert decision.requires_human_review is True


# ----------------------------------------------------------------------
# 5: AI recommendation can be overridden by deterministic policy
# ----------------------------------------------------------------------
def test_ai_deescalation_is_rejected():
    """Spec's explicit example: Gemini says NO_ACTION, but risk is CRITICAL.
    Policy must NOT follow the AI down."""
    cluster = _scored_cluster(RiskLevel.CRITICAL, 90.0)
    investigation = _investigation(
        classification=Classification.NORMAL_ACTIVITY,
        recommended_action=RecommendedAction.NO_ACTION,
        confidence=0.95,
    )
    decision = PolicyEngine().evaluate(cluster, investigation)
    assert decision.decision == PolicyDecisionType.ESCALATE  # NOT NO_ACTION
    assert decision.ai_recommendation == RecommendedAction.NO_ACTION
    assert decision.ai_recommendation_followed is False
    assert ReasonCode.AI_DEESCALATION_REJECTED in decision.reason_codes


def test_ai_escalation_rejected_when_confidence_too_low():
    """Gemini says ESCALATE but risk is only LOW and confidence is weak --
    policy should not blindly amplify a low-confidence AI escalation."""
    cluster = _scored_cluster(RiskLevel.LOW, 10.0)
    investigation = _investigation(
        classification=Classification.INSUFFICIENT_EVIDENCE,
        recommended_action=RecommendedAction.ESCALATE,
        confidence=0.3,
    )
    config = PolicyConfig(min_confidence_for_ai_escalation=0.6)
    decision = PolicyEngine(config).evaluate(cluster, investigation)
    assert decision.decision == PolicyDecisionType.NO_ACTION  # baseline held
    assert ReasonCode.AI_ESCALATION_REJECTED_LOW_CONFIDENCE in decision.reason_codes


def test_ai_escalation_accepted_with_high_confidence():
    cluster = _scored_cluster(RiskLevel.LOW, 10.0)
    investigation = _investigation(
        classification=Classification.POTENTIAL_COORDINATED_ABUSE,
        recommended_action=RecommendedAction.ESCALATE,
        confidence=0.9,
    )
    config = PolicyConfig(min_confidence_for_ai_escalation=0.6)
    decision = PolicyEngine(config).evaluate(cluster, investigation)
    assert decision.decision == PolicyDecisionType.ESCALATE
    assert decision.ai_recommendation_followed is True
    assert ReasonCode.AI_RECOMMENDATION_ACCEPTED in decision.reason_codes


def test_ai_escalation_rejected_for_legitimate_classification_even_with_high_confidence():
    cluster = _scored_cluster(RiskLevel.LOW, 10.0)
    investigation = _investigation(
        classification=Classification.LEGITIMATE_SHARED_INFRASTRUCTURE,
        recommended_action=RecommendedAction.ESCALATE,  # internally inconsistent AI output
        confidence=0.95,
    )
    decision = PolicyEngine().evaluate(cluster, investigation)
    assert decision.decision == PolicyDecisionType.NO_ACTION
    assert ReasonCode.AI_ESCALATION_REJECTED_LEGITIMATE_CLASSIFICATION in decision.reason_codes


def test_ai_unavailable_still_produces_a_decision():
    """If M4 failed entirely, policy must still produce a sound,
    risk-driven decision -- never block on AI availability."""
    cluster = _scored_cluster(RiskLevel.HIGH, 55.0)
    investigation = _investigation(status=InvestigationStatus.AI_UNAVAILABLE, recommended_action=None)
    decision = PolicyEngine().evaluate(cluster, investigation)
    assert decision.decision == PolicyDecisionType.HOLD_FOR_REVIEW  # pure risk-level baseline
    assert decision.ai_recommendation is None
    assert ReasonCode.AI_UNAVAILABLE in decision.reason_codes


# ----------------------------------------------------------------------
# 6-7: Determinism, policy version
# ----------------------------------------------------------------------
def test_policy_decision_is_deterministic():
    cluster = _scored_cluster(RiskLevel.HIGH, 55.0, estimated_exposure=20000.0)
    investigation = _investigation(recommended_action=RecommendedAction.HOLD_FOR_REVIEW, confidence=0.7)
    d1 = PolicyEngine().evaluate(cluster, investigation)
    d2 = PolicyEngine().evaluate(cluster, investigation)
    assert d1.decision == d2.decision
    assert d1.reason_codes == d2.reason_codes
    assert d1.requires_human_review == d2.requires_human_review


def test_policy_version_is_recorded():
    cluster = _scored_cluster(RiskLevel.LOW, 10.0)
    investigation = _investigation()
    config = PolicyConfig(policy_version="v1-test")
    decision = PolicyEngine(config).evaluate(cluster, investigation)
    assert decision.policy_version == "v1-test"


# ----------------------------------------------------------------------
# 8: Single weak signal does not independently trigger extreme policy
# ----------------------------------------------------------------------
def test_single_weak_signal_does_not_trigger_extreme_policy():
    """A cluster with a LOW M3 risk score (M3 already ensures a single
    weak relationship signal can't drive risk high -- see M3 tests)
    must not somehow reach ESCALATE/HOLD_FOR_REVIEW through the policy
    layer either."""
    cluster = _scored_cluster(RiskLevel.LOW, 12.5, estimated_exposure=100.0)
    investigation = _investigation(
        classification=Classification.LEGITIMATE_SHARED_INFRASTRUCTURE,
        recommended_action=RecommendedAction.NO_ACTION,
        confidence=0.9,
    )
    decision = PolicyEngine().evaluate(cluster, investigation)
    assert decision.decision in (PolicyDecisionType.NO_ACTION, PolicyDecisionType.MONITOR)
    assert decision.requires_human_review is False


# ----------------------------------------------------------------------
# Exposure escalation
# ----------------------------------------------------------------------
def test_significant_exposure_escalates_one_step():
    config = PolicyConfig(high_exposure_threshold=15000.0)
    cluster = _scored_cluster(RiskLevel.LOW, 10.0, estimated_exposure=20000.0)  # above threshold
    investigation = _investigation(recommended_action=RecommendedAction.NO_ACTION)
    decision = PolicyEngine(config).evaluate(cluster, investigation)
    # LOW baseline is NO_ACTION; exposure bumps one step to MONITOR.
    assert decision.decision == PolicyDecisionType.MONITOR
    assert ReasonCode.SIGNIFICANT_FINANCIAL_EXPOSURE in decision.reason_codes


def test_exposure_below_threshold_does_not_escalate():
    config = PolicyConfig(high_exposure_threshold=15000.0)
    cluster = _scored_cluster(RiskLevel.LOW, 10.0, estimated_exposure=500.0)
    investigation = _investigation(recommended_action=RecommendedAction.NO_ACTION)
    decision = PolicyEngine(config).evaluate(cluster, investigation)
    assert decision.decision == PolicyDecisionType.NO_ACTION
    assert ReasonCode.SIGNIFICANT_FINANCIAL_EXPOSURE not in decision.reason_codes


# ----------------------------------------------------------------------
# Contradicting evidence acknowledgment
# ----------------------------------------------------------------------
def test_contradicting_evidence_is_noted_in_reason_codes():
    cluster = _scored_cluster(RiskLevel.MEDIUM, 40.0)
    investigation = _investigation(
        recommended_action=RecommendedAction.MONITOR,
        contradicting_evidence=["Transaction velocity is at baseline."],
    )
    decision = PolicyEngine().evaluate(cluster, investigation)
    assert ReasonCode.CONTRADICTING_EVIDENCE_PRESENT in decision.reason_codes


def test_insufficient_evidence_forces_human_review():
    cluster = _scored_cluster(RiskLevel.LOW, 15.0)
    investigation = _investigation(
        classification=Classification.INSUFFICIENT_EVIDENCE,
        recommended_action=RecommendedAction.MONITOR,
        confidence=0.4,
    )
    decision = PolicyEngine().evaluate(cluster, investigation)
    assert decision.requires_human_review is True
    assert ReasonCode.INSUFFICIENT_EVIDENCE in decision.reason_codes
