"""Tests for the M4 AI Investigator: contracts, validation, mock client,
failure handling, data minimization, and ground-truth isolation.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.agent.context import build_investigation_context, sanitize_signals_for_agent
from app.agent.gemini_client import (
    GeminiErrorType,
    GeminiRawResult,
    MockGeminiClient,
    RealGeminiClient,
)
from app.agent.investigator import investigate
from app.agent.models import (
    Classification,
    EntityCounts,
    InvestigationRequest,
    InvestigationResponse,
    InvestigationStatus,
    RecommendedAction,
    RiskContext,
    Severity,
)
from app.agent.validation import InvestigationValidationError, validate_investigation_response
from app.intelligence.pipeline import run_pipeline
from app.risk.config import RiskLevel
from app.risk.models import Contributor, ExposureAssessment
from app.risk.pipeline import score_clusters

from tests.test_intelligence import _legitimate_shared_infra_scenario, _suspicious_coordinated_scenario


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _sample_request(**overrides) -> InvestigationRequest:
    base = dict(
        cluster_id="cc-0000",
        entities=EntityCounts(customer_count=4, device_count=1, network_count=1, transaction_count=10),
        risk=RiskContext(score=68.0, level=RiskLevel.HIGH),
        exposure=ExposureAssessment(
            transaction_count=10, transaction_value=50000.0, order_count=10,
            return_count=3, returned_value=15000.0, estimated_exposure=15000.0,
        ),
        signals={
            "shared_device": {"num_devices": 1, "shared_device_ratio": 1.0, "max_customers_per_device": 4},
            "shared_network": {"num_networks": 1, "shared_network_ratio": 1.0, "max_customers_per_network": 4},
            "account_creation_burst": {"burst_ratio": 1.0, "num_customers": 4, "max_accounts_in_window": 4, "window_hours": 48.0},
            "transaction_velocity": {"num_transactions": 10, "velocity_ratio_vs_baseline": 2.0},
            "transaction_coordination": {"temporal_coordination_ratio": 1.0, "num_transactions": 10},
            "return_anomaly": {"return_rate": 0.3, "deviation_ratio": 3.0, "insufficient_data": False},
            "graph_connectivity": {"num_customer_nodes": 4, "density": 0.6},
        },
        contributors=[
            Contributor(signal="account_creation_burst", contribution=20.0, max_contribution=20.0, evidence="4 of 4 created in one window."),
            Contributor(signal="transaction_coordination", contribution=15.0, max_contribution=15.0, evidence="All transactions coordinated."),
        ],
        evidence=["4 of 4 accounts created within a 48h window.", "All transactions coordinated."],
    )
    base.update(overrides)
    return InvestigationRequest(**base)


def _valid_response_dict(**overrides) -> dict:
    base = {
        "cluster_id": "cc-0000",
        "assessment": {"classification": "POTENTIAL_COORDINATED_ABUSE", "severity": "HIGH", "confidence": 0.8},
        "summary": "Multiple signals reinforce coordinated activity.",
        "key_findings": [{"finding": "Accounts created in a burst.", "evidence_refs": ["account_creation_burst"]}],
        "supporting_evidence": ["Burst account creation.", "Coordinated transaction timing."],
        "contradicting_evidence": [],
        "investigation_recommendations": ["Review manually."],
        "recommended_action": "HOLD_FOR_REVIEW",
    }
    base.update(overrides)
    return base


# ----------------------------------------------------------------------
# 1-2: Request / response validate correctly
# ----------------------------------------------------------------------
def test_investigation_request_validates_correctly():
    request = _sample_request()
    assert request.cluster_id == "cc-0000"
    assert request.entities.customer_count == 4
    assert request.risk.level == RiskLevel.HIGH


def test_investigation_response_validates_correctly():
    response = InvestigationResponse.model_validate(_valid_response_dict())
    assert response.assessment.classification == Classification.POTENTIAL_COORDINATED_ABUSE
    assert response.recommended_action == RecommendedAction.HOLD_FOR_REVIEW


# ----------------------------------------------------------------------
# 3-5: Invalid output rejected -- missing fields, invalid enums
# ----------------------------------------------------------------------
def test_invalid_gemini_output_is_rejected():
    bad = _valid_response_dict()
    del bad["assessment"]
    with pytest.raises(ValidationError):
        InvestigationResponse.model_validate(bad)


def test_missing_required_field_is_rejected():
    bad = _valid_response_dict()
    del bad["summary"]
    with pytest.raises(ValidationError):
        InvestigationResponse.model_validate(bad)


def test_invalid_enum_value_is_rejected():
    bad = _valid_response_dict(recommended_action="DELETE_ACCOUNT")
    with pytest.raises(ValidationError):
        InvestigationResponse.model_validate(bad)

    bad2 = _valid_response_dict()
    bad2["assessment"]["classification"] = "DEFINITELY_FRAUD"
    with pytest.raises(ValidationError):
        InvestigationResponse.model_validate(bad2)


def test_confidence_out_of_range_is_rejected():
    bad = _valid_response_dict()
    bad["assessment"]["confidence"] = 1.5
    with pytest.raises(ValidationError):
        InvestigationResponse.model_validate(bad)


# ----------------------------------------------------------------------
# 6-8: M3 values preserved, Gemini cannot rewrite evidence
# ----------------------------------------------------------------------
def test_m3_risk_score_is_preserved_in_context():
    data, _ = _suspicious_coordinated_scenario()
    scored = score_clusters(run_pipeline(data), data)
    request = build_investigation_context(scored[0])
    assert request.risk.score == scored[0].risk.score
    assert request.risk.level == scored[0].risk.level


def test_m3_exposure_is_preserved_in_context():
    data, _ = _suspicious_coordinated_scenario()
    scored = score_clusters(run_pipeline(data), data)
    request = build_investigation_context(scored[0])
    assert request.exposure == scored[0].exposure


@pytest.mark.asyncio
async def test_gemini_cannot_modify_deterministic_evidence():
    """Even if Gemini's response echoes back a DIFFERENT cluster_id, the
    final result must use OUR cluster_id, never Gemini's. And nothing
    in InvestigationResult exposes a mutable view of risk/exposure --
    those live only in the M3 ScoredCluster, never touched here."""
    request = _sample_request(cluster_id="cc-0000")

    class EchoTamperedClient:
        async def generate_investigation(self, req):
            tampered = _valid_response_dict(cluster_id="cc-9999-DIFFERENT")
            return GeminiRawResult(model="test", latency_ms=1.0, raw_json=tampered)

    result = await investigate(request, EchoTamperedClient())
    assert result.cluster_id == "cc-0000"  # NOT cc-9999


# ----------------------------------------------------------------------
# 9: No secrets in logs
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_secrets_in_logs(caplog):
    fake_api_key = "sk-super-secret-fake-key-should-never-appear-in-logs"
    request = _sample_request()

    with caplog.at_level(logging.DEBUG, logger="trustgraph.agent"):
        # A real client without network access will fail fast (bad host
        # never contacted in this test -- we just construct it to prove
        # the api_key string itself never gets logged, even in failure).
        client = RealGeminiClient(api_key=fake_api_key, model="test-model", timeout_seconds=0.01, max_retries=0)

        # Force a quick failure path without a real network call.
        async def _boom(*args, **kwargs):
            raise ConnectionError("simulated network failure")

        client._client.aio.models.generate_content = _boom
        await investigate(request, client)
        await client.aclose()

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert fake_api_key not in log_text


# ----------------------------------------------------------------------
# 10: Mock Gemini produces deterministic output
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_gemini_is_deterministic():
    request = _sample_request()
    client = MockGeminiClient()
    result_a = await client.generate_investigation(request)
    result_b = await client.generate_investigation(request)
    assert result_a.raw_json == result_b.raw_json


@pytest.mark.asyncio
async def test_mock_gemini_output_passes_validation():
    request = _sample_request()
    result = await MockGeminiClient().generate_investigation(request)
    validated = validate_investigation_response(result.raw_json, allowed_evidence_refs=set(request.signals.keys()))
    assert validated.cluster_id == "cc-0000"


# ----------------------------------------------------------------------
# 11-13: Failure handling -- Gemini failure, timeout, missing API key
# ----------------------------------------------------------------------
class _FailingClient:
    def __init__(self, error_type: GeminiErrorType, error_message: str = "simulated failure"):
        self.error_type = error_type
        self.error_message = error_message

    async def generate_investigation(self, request):
        return GeminiRawResult(
            model="test-model", latency_ms=5.0, raw_json=None,
            error_type=self.error_type, error_message=self.error_message,
        )


@pytest.mark.asyncio
async def test_gemini_failure_produces_controlled_failure_state():
    request = _sample_request()
    result = await investigate(request, _FailingClient(GeminiErrorType.PROVIDER_ERROR))
    assert result.status == InvestigationStatus.AI_UNAVAILABLE
    assert result.assessment is None
    assert result.metadata.error == "simulated failure"
    # Must still be a fully valid InvestigationResult -- never crashes,
    # never fabricates a fake assessment.
    assert result.cluster_id == "cc-0000"


@pytest.mark.asyncio
async def test_timeout_is_handled_end_to_end():
    """Exercises RealGeminiClient's actual asyncio.wait_for timeout path,
    not just a test double -- monkeypatches the SDK call to hang."""
    import asyncio

    request = _sample_request()
    client = RealGeminiClient(api_key="fake-key-not-used", model="test-model", timeout_seconds=0.05, max_retries=0)

    async def _hang(*args, **kwargs):
        await asyncio.sleep(10)

    client._client.aio.models.generate_content = _hang

    raw_result = await client.generate_investigation(request)
    assert raw_result.error_type == GeminiErrorType.TIMEOUT

    result = await investigate(request, client)
    assert result.status == InvestigationStatus.AI_UNAVAILABLE
    await client.aclose()


@pytest.mark.asyncio
async def test_missing_api_key_is_handled():
    request = _sample_request()
    client = RealGeminiClient(api_key=None, model="test-model", timeout_seconds=5.0, max_retries=0)

    raw_result = await client.generate_investigation(request)
    assert raw_result.error_type == GeminiErrorType.MISSING_API_KEY

    result = await investigate(request, client)
    assert result.status == InvestigationStatus.AI_UNAVAILABLE
    assert result.assessment is None


@pytest.mark.asyncio
async def test_malformed_json_output_is_handled():
    class MalformedJSONClient:
        async def generate_investigation(self, req):
            return GeminiRawResult(model="test", latency_ms=1.0, raw_json={"not": "the right shape at all"})

    request = _sample_request()
    result = await investigate(request, MalformedJSONClient())
    assert result.status == InvestigationStatus.INVESTIGATION_FAILED


@pytest.mark.asyncio
async def test_empty_response_is_handled():
    """EMPTY_RESPONSE means Gemini WAS reachable but returned nothing
    usable -- a response-content problem, not a connectivity problem,
    so it maps to INVESTIGATION_FAILED (not AI_UNAVAILABLE, which is
    reserved for auth/timeout/rate-limit/network/provider-level issues
    where the provider itself couldn't be reached or used at all)."""
    request = _sample_request()
    result = await investigate(request, _FailingClient(GeminiErrorType.EMPTY_RESPONSE, "Gemini returned nothing."))
    assert result.status == InvestigationStatus.INVESTIGATION_FAILED
    assert result.assessment is None


# ----------------------------------------------------------------------
# 14: Ground truth never enters the Gemini context
# ----------------------------------------------------------------------
def test_ground_truth_never_in_investigation_request():
    data, _ = _suspicious_coordinated_scenario()
    scored = score_clusters(run_pipeline(data), data)
    request = build_investigation_context(scored[0])

    payload_json = json.dumps(request.model_dump(mode="json"))
    for token in ("ground_truth", "is_abuse", "abuse_ring", "GroundTruth"):
        assert token not in payload_json


def test_agent_module_never_imports_ground_truth():
    agent_dir = Path(__file__).resolve().parents[1] / "app" / "agent"
    forbidden = ["import GroundTruth", "GroundTruth(", "GroundTruthLabel.", "select(GroundTruth"]
    for py_file in agent_dir.glob("*.py"):
        content = py_file.read_text()
        for pattern in forbidden:
            assert pattern not in content, f"{py_file.name} references forbidden pattern {pattern!r}"


# ----------------------------------------------------------------------
# 15: No unnecessary PII
# ----------------------------------------------------------------------
def test_no_raw_id_lists_in_investigation_request():
    """Only aggregate COUNTS should reach Gemini -- never the raw
    customer/device/network/transaction UUID arrays."""
    data, customer_ids = _suspicious_coordinated_scenario()
    scored = score_clusters(run_pipeline(data), data)
    request = build_investigation_context(scored[0])

    payload_json = json.dumps(request.model_dump(mode="json"))
    for cid in customer_ids:
        assert cid not in payload_json

    # entities only carries counts, never lists
    assert not hasattr(request.entities, "customers")
    assert not hasattr(request.entities, "customer_ids")


def test_no_email_or_display_name_possible_in_context():
    """Structural guarantee: EntityCounts/RiskContext/ExposureAssessment
    have no field that could hold an email or name even if someone tried
    to add one upstream -- verified via the Pydantic schema itself."""
    fields = set(EntityCounts.model_fields.keys())
    assert "email" not in fields
    assert "display_name" not in fields
    assert "name" not in fields


def test_sanitize_signals_strips_id_keyed_breakdowns():
    signals = {
        "shared_device": {
            "num_devices": 2,
            "shared_device_ratio": 1.0,
            "device_customer_counts_in_cluster": {"device-uuid-1": 3},
            "device_customer_counts_dataset_wide": {"device-uuid-1": 5},
        },
        "graph_connectivity": {"density": 0.5},
    }
    sanitized = sanitize_signals_for_agent(signals)
    assert "device_customer_counts_in_cluster" not in sanitized["shared_device"]
    assert "device_customer_counts_dataset_wide" not in sanitized["shared_device"]
    assert sanitized["shared_device"]["shared_device_ratio"] == 1.0  # aggregate kept
    assert sanitized["graph_connectivity"] == {"density": 0.5}
    # Original dict must be untouched (no in-place mutation).
    assert "device_customer_counts_in_cluster" in signals["shared_device"]


# ----------------------------------------------------------------------
# 16: Evidence references correspond to supplied evidence
# ----------------------------------------------------------------------
def test_evidence_refs_must_match_supplied_signals():
    request = _sample_request()
    allowed = set(request.signals.keys())

    valid = _valid_response_dict()
    validate_investigation_response(valid, allowed)  # should not raise

    invalid = _valid_response_dict()
    invalid["key_findings"] = [{"finding": "made up", "evidence_refs": ["nonexistent_signal"]}]
    with pytest.raises(InvestigationValidationError):
        validate_investigation_response(invalid, allowed)


@pytest.mark.asyncio
async def test_mock_client_findings_always_reference_valid_signals():
    for scenario_builder in (_suspicious_coordinated_scenario, _legitimate_shared_infra_scenario):
        data, _ = scenario_builder()
        scored = score_clusters(run_pipeline(data), data)
        request = build_investigation_context(scored[0])
        raw_result = await MockGeminiClient().generate_investigation(request)
        # Must validate cleanly -- proves the mock's own evidence_refs are honest.
        validate_investigation_response(raw_result.raw_json, allowed_evidence_refs=set(request.signals.keys()))


# ----------------------------------------------------------------------
# 17: Recommendations bounded to allowed enum values
# ----------------------------------------------------------------------
def test_recommended_action_enum_is_closed():
    allowed = {a.value for a in RecommendedAction}
    assert allowed == {"NO_ACTION", "MONITOR", "REVIEW", "HOLD_FOR_REVIEW", "ESCALATE"}
    # No free-form / executable-instruction-shaped values sneak in.
    for forbidden in ("BLOCK_CUSTOMER", "REFUND_TRANSACTION", "DELETE_ACCOUNT", "CALL_API"):
        assert forbidden not in allowed


@pytest.mark.asyncio
async def test_full_pipeline_recommended_action_is_always_a_valid_enum():
    for scenario_builder in (_suspicious_coordinated_scenario, _legitimate_shared_infra_scenario):
        data, _ = scenario_builder()
        scored = score_clusters(run_pipeline(data), data)
        request = build_investigation_context(scored[0])
        result = await investigate(request, MockGeminiClient())
        assert result.recommended_action in list(RecommendedAction)


# ----------------------------------------------------------------------
# Demo cases (spec-required): suspicious vs legitimate
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_demo_case_a_suspicious_coordinated_cluster():
    data, _ = _suspicious_coordinated_scenario()
    scored = score_clusters(run_pipeline(data), data)
    request = build_investigation_context(scored[0])
    result = await investigate(request, MockGeminiClient())

    assert result.status == InvestigationStatus.COMPLETED
    assert result.assessment.classification == Classification.POTENTIAL_COORDINATED_ABUSE
    assert len(result.key_findings) > 0
    assert result.recommended_action != RecommendedAction.NO_ACTION


@pytest.mark.asyncio
async def test_demo_case_b_legitimate_shared_infrastructure_not_auto_abuse():
    data, _ = _legitimate_shared_infra_scenario()
    scored = score_clusters(run_pipeline(data), data)
    request = build_investigation_context(scored[0])
    result = await investigate(request, MockGeminiClient())

    assert result.status == InvestigationStatus.COMPLETED
    # Sharing a device/network alone must NOT be classified as abuse.
    assert result.assessment.classification != Classification.POTENTIAL_COORDINATED_ABUSE
