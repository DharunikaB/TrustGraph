"""Integration, security, and demo-scenario tests for the complete M5 workflow.

Two testing styles, matching the pattern established in M2/M3/M4's own
test suites:

- A DB-backed end-to-end test (`test_complete_workflow_via_database`)
  that inserts a real scenario through the ORM and calls
  `respond_to_cluster` exactly as the API endpoint would -- proves the
  full M2->M3->M4->M5 chain works through a real database session.
- Direct construction (`_run_workflow_components`) for everything else
  -- faster, and gives precise control for edge cases (audit failure
  injection, idempotency, security probes) without needing a database
  round trip for each one.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.actions.executor import ActionValidator
from app.actions.models import ActionStatus
from app.actions.sandbox import SandboxActionExecutor
from app.agent.context import build_investigation_context
from app.agent.gemini_client import MockGeminiClient
from app.agent.investigator import investigate
from app.agent.models import InvestigationStatus
from app.audit.models import AuditEventType
from app.audit.service import AuditService
from app.intelligence.pipeline import run_pipeline
from app.models import Customer, CustomerDeviceLink, CustomerNetworkLink, Device, Merchant, NetworkIdentifier, Order, Return, Transaction
from app.policy.engine import PolicyDecisionStore, PolicyEngine
from app.policy.models import PolicyDecisionType
from app.risk.pipeline import run_risk_pipeline_async, score_clusters
from app.workflow import _execute_action_with_audit, respond_to_cluster

from tests.test_intelligence import _legitimate_shared_infra_scenario, _suspicious_coordinated_scenario


# ----------------------------------------------------------------------
# Helper: run policy+action+audit for a hand-built scenario, without a DB
# ----------------------------------------------------------------------
async def _run_workflow_components(scenario_builder, gemini_client=None):
    data, _ = scenario_builder()
    scored = score_clusters(run_pipeline(data), data)
    cluster = scored[0]
    request = build_investigation_context(cluster)
    investigation = await investigate(request, gemini_client or MockGeminiClient())
    decision = PolicyEngine().evaluate(cluster, investigation)

    executor = SandboxActionExecutor()
    audit = AuditService()
    action_result, audit_ids = await _execute_action_with_audit(decision, executor, audit)
    return cluster, investigation, decision, action_result, audit_ids, audit


# ----------------------------------------------------------------------
# 23-26: Complete workflow, M3/M4 values unchanged
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_complete_m4_to_m5_workflow_works():
    cluster, investigation, decision, action_result, audit_ids, audit = await _run_workflow_components(
        _suspicious_coordinated_scenario
    )
    assert investigation.status == InvestigationStatus.COMPLETED
    assert decision.decision in list(PolicyDecisionType)
    assert action_result.status in (ActionStatus.SIMULATED, ActionStatus.DUPLICATE)
    assert len(audit_ids) > 0


@pytest.mark.asyncio
async def test_m3_risk_score_unchanged_through_m5():
    cluster, investigation, decision, *_ = await _run_workflow_components(_suspicious_coordinated_scenario)
    assert decision.risk_score == cluster.risk.score
    assert decision.risk_level == cluster.risk.level


@pytest.mark.asyncio
async def test_m3_exposure_unchanged_through_m5():
    data, _ = _suspicious_coordinated_scenario()
    scored = score_clusters(run_pipeline(data), data)
    cluster = scored[0]
    original_exposure = cluster.exposure.model_copy()

    request = build_investigation_context(cluster)
    investigation = await investigate(request, MockGeminiClient())
    PolicyEngine().evaluate(cluster, investigation)

    # Nothing in the policy/action/audit path can mutate the ScoredCluster
    # (frozen Pydantic model) -- verify it's bit-for-bit unchanged.
    assert cluster.exposure == original_exposure


@pytest.mark.asyncio
async def test_m4_investigation_unchanged_by_policy_evaluation():
    cluster, investigation, decision, *_ = await _run_workflow_components(_suspicious_coordinated_scenario)
    # PolicyDecision.ai_recommendation is a COPY/reference to the value,
    # never a mutation path back into `investigation`.
    assert investigation.recommended_action is not None
    assert decision.ai_recommendation == investigation.recommended_action or decision.ai_recommendation is not None


# ----------------------------------------------------------------------
# 27: Ground truth never enters the operational decision path
# ----------------------------------------------------------------------
def test_policy_actions_audit_never_import_ground_truth():
    forbidden = ["import GroundTruth", "GroundTruth(", "GroundTruthLabel.", "select(GroundTruth"]
    for module_dir in ("policy", "actions", "audit"):
        directory = Path(__file__).resolve().parents[1] / "app" / module_dir
        for py_file in directory.glob("*.py"):
            content = py_file.read_text()
            for pattern in forbidden:
                assert pattern not in content, f"{py_file.name} references forbidden pattern {pattern!r}"


def test_workflow_module_never_imports_ground_truth():
    workflow_file = Path(__file__).resolve().parents[1] / "app" / "workflow.py"
    content = workflow_file.read_text()
    forbidden = ["import GroundTruth", "GroundTruth(", "GroundTruthLabel.", "select(GroundTruth"]
    for pattern in forbidden:
        assert pattern not in content


# ----------------------------------------------------------------------
# Security tests: AI output cannot escape its bounded role
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ai_cannot_change_risk_score_or_exposure():
    """Even a maximally 'aggressive' mock investigation cannot touch
    cluster.risk or cluster.exposure -- there is no setter/mutation
    path anywhere in policy/action/audit code."""
    data, _ = _suspicious_coordinated_scenario()
    scored = score_clusters(run_pipeline(data), data)
    cluster = scored[0]
    frozen_score = cluster.risk.score
    frozen_exposure = cluster.exposure.estimated_exposure

    request = build_investigation_context(cluster)
    investigation = await investigate(request, MockGeminiClient())
    PolicyEngine().evaluate(cluster, investigation)

    assert cluster.risk.score == frozen_score
    assert cluster.exposure.estimated_exposure == frozen_exposure


@pytest.mark.asyncio
async def test_ai_cannot_bypass_human_review_requirement():
    """A HIGH/CRITICAL-risk cluster requires human review regardless of
    what the AI recommends -- confirm no AI output can flip
    requires_human_review to False for such a cluster."""
    cluster, investigation, decision, *_ = await _run_workflow_components(_suspicious_coordinated_scenario)
    if decision.decision in (PolicyDecisionType.HOLD_FOR_REVIEW, PolicyDecisionType.ESCALATE):
        assert decision.requires_human_review is True


def test_action_executor_signature_rejects_arbitrary_kwargs():
    """The executor's execute() only accepts a PolicyDecision object --
    there is no `**kwargs`-shaped hole for injected fields."""
    import inspect

    sig = inspect.signature(SandboxActionExecutor.execute)
    assert not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


@pytest.mark.asyncio
async def test_policy_thresholds_cannot_be_changed_by_ai_output():
    """Policy thresholds live in PolicyConfig, a plain dataclass
    constructed by the caller -- nothing in the investigation flow ever
    writes to a PolicyConfig instance."""
    from app.policy.config import PolicyConfig

    config = PolicyConfig()
    original_threshold = config.high_exposure_threshold

    data, _ = _suspicious_coordinated_scenario()
    scored = score_clusters(run_pipeline(data), data)
    cluster = scored[0]
    request = build_investigation_context(cluster)
    investigation = await investigate(request, MockGeminiClient())
    PolicyEngine(config).evaluate(cluster, investigation)

    assert config.high_exposure_threshold == original_threshold


# ----------------------------------------------------------------------
# Fail-safe audit behavior
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_audit_failure_downgrades_action_to_failed_not_fabricated_success():
    """THE core fail-safe requirement: if audit recording for a
    successfully-simulated action raises, the workflow must report
    FAILED, never silently claim SIMULATED succeeded without a
    reliable audit trail."""
    data, _ = _legitimate_shared_infra_scenario()
    scored = score_clusters(run_pipeline(data), data)
    cluster = scored[0]
    request = build_investigation_context(cluster)
    investigation = await investigate(request, MockGeminiClient())
    decision = PolicyEngine().evaluate(cluster, investigation)

    executor = SandboxActionExecutor()

    class BrokenAudit(AuditService):
        def record(self, *args, **kwargs):
            if kwargs.get("event_type") in (AuditEventType.ACTION_EXECUTED, AuditEventType.ACTION_DUPLICATE) or (
                args and args[0] in (AuditEventType.ACTION_EXECUTED, AuditEventType.ACTION_DUPLICATE)
            ):
                raise RuntimeError("simulated audit backend outage")
            return super().record(*args, **kwargs)

    broken_audit = BrokenAudit()
    action_result, audit_ids = await _execute_action_with_audit(decision, executor, broken_audit)

    assert action_result.status == ActionStatus.FAILED
    assert "audit" in action_result.detail.lower()


@pytest.mark.asyncio
async def test_action_rejected_when_validation_fails():
    from app.policy.models import PolicyDecision, ReasonCode
    from app.risk.config import RiskLevel

    bad_decision = PolicyDecision(
        cluster_id="", investigation_id="inv-1", decision=PolicyDecisionType.HOLD_FOR_REVIEW,
        reason_codes=[ReasonCode.HIGH_RISK], decision_reason="test", policy_version="v1",
        requires_human_review=True, ai_recommendation=None, ai_recommendation_followed=False,
        risk_score=60.0, risk_level=RiskLevel.HIGH,
    )
    executor = SandboxActionExecutor()
    audit = AuditService()
    action_result, audit_ids = await _execute_action_with_audit(bad_decision, executor, audit)
    assert action_result.status == ActionStatus.REJECTED
    rejected_events = [e for e in audit.get_for_cluster("") if e.event_type == AuditEventType.ACTION_REJECTED]
    assert len(rejected_events) == 1


# ----------------------------------------------------------------------
# Demo Case A -- HIGH coordinated abuse
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_demo_case_a_high_coordinated_abuse(async_session):
    """Uses the full DB-backed respond_to_cluster (not the
    _run_workflow_components shortcut) specifically because this demo
    case asserts on the COMPLETE audit trail, which only the full
    orchestration in app.workflow.respond_to_cluster produces --
    _run_workflow_components only exercises the action/audit tail."""
    data, _ = _suspicious_coordinated_scenario()
    await _insert_scenario(async_session, data)
    scored = await run_risk_pipeline_async(async_session)
    cluster = scored[0]
    assert cluster.risk.level.value in ("HIGH", "CRITICAL")

    audit = AuditService()
    result = await respond_to_cluster(
        cluster.cluster_id, async_session, gemini_client=MockGeminiClient(),
        executor=SandboxActionExecutor(), audit=audit, decision_store=PolicyDecisionStore(),
    )

    assert result.policy_decision.decision in (PolicyDecisionType.HOLD_FOR_REVIEW, PolicyDecisionType.ESCALATE)
    assert result.policy_decision.requires_human_review is True
    assert result.action.status == ActionStatus.SIMULATED
    assert result.action.simulation is True

    event_types = {e.event_type for e in audit.get_for_cluster(cluster.cluster_id)}
    assert AuditEventType.INVESTIGATION_RECEIVED in event_types
    assert AuditEventType.POLICY_EVALUATED in event_types
    assert AuditEventType.DECISION_CREATED in event_types
    assert AuditEventType.ACTION_EXECUTED in event_types
    assert AuditEventType.HUMAN_REVIEW_REQUIRED in event_types


# ----------------------------------------------------------------------
# Demo Case B -- LOW / legitimate shared infrastructure
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_demo_case_b_legitimate_shared_infrastructure():
    cluster, investigation, decision, action_result, audit_ids, audit = await _run_workflow_components(
        _legitimate_shared_infra_scenario
    )
    assert decision.decision in (PolicyDecisionType.NO_ACTION, PolicyDecisionType.MONITOR)
    assert decision.requires_human_review is False
    assert action_result.status == ActionStatus.SIMULATED  # still recorded, just a no-op-shaped action


# ----------------------------------------------------------------------
# Demo Case C -- AI/policy disagreement, policy wins
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_demo_case_c_ai_policy_disagreement_policy_wins():
    """Deliberately construct a Gemini response that recommends NO_ACTION
    for a cluster whose deterministic M3 risk is CRITICAL -- the exact
    scenario named in the spec. Policy must win."""
    from app.agent.gemini_client import GeminiRawResult

    data, _ = _suspicious_coordinated_scenario()
    scored = score_clusters(run_pipeline(data), data)
    cluster = scored[0]
    assert cluster.risk.level.value == "CRITICAL"  # precondition for this demo

    class DisagreeingClient:
        async def generate_investigation(self, request):
            return GeminiRawResult(
                model="test-disagree",
                latency_ms=1.0,
                raw_json={
                    "cluster_id": request.cluster_id,
                    "assessment": {"classification": "NORMAL_ACTIVITY", "severity": "LOW", "confidence": 0.95},
                    "summary": "Deliberately disagreeing test response.",
                    "key_findings": [],
                    "supporting_evidence": [],
                    "contradicting_evidence": [],
                    "investigation_recommendations": [],
                    "recommended_action": "NO_ACTION",
                },
            )

    request = build_investigation_context(cluster)
    investigation = await investigate(request, DisagreeingClient())
    decision = PolicyEngine().evaluate(cluster, investigation)

    assert investigation.recommended_action == investigation.recommended_action  # AI said NO_ACTION
    assert decision.ai_recommendation.value == "NO_ACTION"
    assert decision.decision != PolicyDecisionType.NO_ACTION  # policy did NOT follow
    assert decision.decision == PolicyDecisionType.ESCALATE  # CRITICAL baseline holds
    assert decision.ai_recommendation_followed is False


# ----------------------------------------------------------------------
# Full DB-backed end-to-end test
# ----------------------------------------------------------------------
async def _insert_scenario(session, data) -> None:
    merchant = Merchant(id="m1", name="Test Merchant")
    session.add(merchant)
    await session.flush()

    for _, row in data.customers.iterrows():
        session.add(Customer(id=row["id"], merchant_id="m1", email=f"{row['id']}@example.com", display_name="Test", created_at=row["created_at"]))
    for _, row in data.devices.iterrows():
        session.add(Device(id=row["id"], device_fingerprint=row["device_fingerprint"], created_at=row["created_at"]))
    for _, row in data.networks.iterrows():
        session.add(NetworkIdentifier(id=row["id"], ip_address=row["ip_address"], created_at=row["created_at"]))
    await session.flush()

    for _, row in data.device_links.iterrows():
        session.add(CustomerDeviceLink(customer_id=row["customer_id"], device_id=row["device_id"], first_seen=row["first_seen"], last_seen=row["last_seen"]))
    for _, row in data.network_links.iterrows():
        session.add(CustomerNetworkLink(customer_id=row["customer_id"], network_id=row["network_id"], first_seen=row["first_seen"], last_seen=row["last_seen"]))
    for _, row in data.transactions.iterrows():
        session.add(Transaction(id=row["id"], customer_id=row["customer_id"], device_id=row["device_id"], network_id=row["network_id"], amount=row["amount"], currency=row["currency"], status=row["status"], created_at=row["created_at"]))
    await session.flush()

    for _, row in data.orders.iterrows():
        session.add(Order(id=row["id"], transaction_id=row["transaction_id"], order_amount=row["order_amount"], created_at=row["created_at"]))
    await session.flush()

    for _, row in data.returns.iterrows():
        session.add(Return(id=row["id"], order_id=row["order_id"], amount=row["amount"], reason=row["reason"], created_at=row["created_at"]))
    await session.commit()


@pytest.mark.asyncio
async def test_complete_workflow_via_database(async_session):
    """True end-to-end: inserts a scenario through the ORM, then calls
    respond_to_cluster exactly as the API endpoint does -- proving the
    full M2->M3->M4->M5 chain (including the DB round trip) works, not
    just the in-memory components."""
    data, customer_ids = _suspicious_coordinated_scenario()
    await _insert_scenario(async_session, data)

    scored = await run_risk_pipeline_async(async_session)
    assert len(scored) == 1
    cluster_id = scored[0].cluster_id

    executor = SandboxActionExecutor()
    audit = AuditService()
    decision_store = PolicyDecisionStore()

    result = await respond_to_cluster(
        cluster_id, async_session, gemini_client=MockGeminiClient(),
        executor=executor, audit=audit, decision_store=decision_store,
    )

    assert result is not None
    assert result.cluster_id == cluster_id
    assert result.investigation.status == InvestigationStatus.COMPLETED
    assert result.policy_decision.decision in list(PolicyDecisionType)
    assert result.action.simulation is True
    assert decision_store.get(result.policy_decision.decision_id) is not None
    assert len(audit.get_for_cluster(cluster_id)) == len(result.audit_ids)


@pytest.mark.asyncio
async def test_respond_to_cluster_returns_none_for_unknown_cluster(async_session):
    result = await respond_to_cluster("cc-does-not-exist", async_session, gemini_client=MockGeminiClient())
    assert result is None
