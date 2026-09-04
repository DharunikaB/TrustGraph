"""Tests for M5's bounded action taxonomy, validator, and sandbox executor."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.actions.executor import ActionValidationError, ActionValidator
from app.actions.models import ActionResult, ActionStatus, ActionTarget, ActionType
from app.actions.sandbox import SandboxActionExecutor
from app.policy.models import PolicyDecision, ReasonCode
from app.risk.config import RiskLevel


def _decision(decision_id: str = "dec-1", action: ActionType = ActionType.HOLD_FOR_REVIEW, cluster_id: str = "cc-test") -> PolicyDecision:
    return PolicyDecision(
        decision_id=decision_id,
        cluster_id=cluster_id,
        investigation_id="inv-1",
        decision=action,
        reason_codes=[ReasonCode.HIGH_RISK],
        decision_reason="test",
        policy_version="v1",
        requires_human_review=True,
        ai_recommendation=None,
        ai_recommendation_followed=False,
        risk_score=60.0,
        risk_level=RiskLevel.HIGH,
    )


# ----------------------------------------------------------------------
# 9-10: Valid action executes, unsupported action rejected
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_valid_action_executes_in_sandbox():
    executor = SandboxActionExecutor()
    result = await executor.execute(_decision())
    assert result.status == ActionStatus.SIMULATED
    assert result.simulation is True


def test_unsupported_action_type_is_rejected_by_pydantic():
    """The action taxonomy is a closed Pydantic enum -- an unsupported
    value can't even construct a PolicyDecision, let alone reach the
    executor."""
    with pytest.raises(ValidationError):
        PolicyDecision(
            cluster_id="cc-test", investigation_id="inv-1",
            decision="DELETE_ACCOUNT",  # not in ActionType
            reason_codes=[], decision_reason="x", policy_version="v1",
            requires_human_review=False, ai_recommendation=None,
            ai_recommendation_followed=False, risk_score=10.0, risk_level=RiskLevel.LOW,
        )


# ----------------------------------------------------------------------
# 11: Gemini cannot inject arbitrary actions
# ----------------------------------------------------------------------
def test_action_type_vocabulary_has_no_executable_instructions():
    """The action taxonomy the validator/executor accept is exactly the
    five bounded categories -- nothing shaped like a command."""
    allowed = {a.value for a in ActionType}
    assert allowed == {"NO_ACTION", "MONITOR", "REVIEW", "HOLD_FOR_REVIEW", "ESCALATE"}
    for forbidden in ("DELETE_ACCOUNT", "REFUND_TRANSACTION", "BLOCK_CUSTOMER", "DROP TABLE", "rm -rf /", "http://evil.example"):
        assert forbidden not in allowed


@pytest.mark.asyncio
async def test_gemini_text_never_reaches_the_executor():
    """The executor's `execute()` signature only accepts a PolicyDecision
    -- there is no parameter through which raw Gemini text (a
    `summary`, `evidence`, etc.) could be passed and interpreted."""
    import inspect

    sig = inspect.signature(SandboxActionExecutor.execute)
    params = list(sig.parameters.keys())
    assert params == ["self", "decision"]


# ----------------------------------------------------------------------
# 12: Invalid target is rejected
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_empty_cluster_id_is_rejected():
    decision = _decision(cluster_id="")
    with pytest.raises(ActionValidationError):
        ActionValidator().validate(decision)

    executor = SandboxActionExecutor()
    with pytest.raises(ActionValidationError):
        await executor.execute(decision)


@pytest.mark.asyncio
async def test_whitespace_only_cluster_id_is_rejected():
    decision = _decision(cluster_id="   ")
    with pytest.raises(ActionValidationError):
        ActionValidator().validate(decision)


# ----------------------------------------------------------------------
# 13: Duplicate action is idempotent
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_decision_id_produces_duplicate_status():
    executor = SandboxActionExecutor()
    decision = _decision(decision_id="fixed-id")

    first = await executor.execute(decision)
    second = await executor.execute(decision)

    assert first.status == ActionStatus.SIMULATED
    assert second.status == ActionStatus.DUPLICATE
    assert second.duplicate_of_action_id == first.action_id
    # No second "effective" (SIMULATED) action was created.
    all_simulated = [
        r for r in (first, second) if r.status == ActionStatus.SIMULATED
    ]
    assert len(all_simulated) == 1


@pytest.mark.asyncio
async def test_different_decision_ids_are_not_treated_as_duplicates():
    executor = SandboxActionExecutor()
    r1 = await executor.execute(_decision(decision_id="dec-a"))
    r2 = await executor.execute(_decision(decision_id="dec-b"))
    assert r1.status == ActionStatus.SIMULATED
    assert r2.status == ActionStatus.SIMULATED  # different decision -> genuinely new


@pytest.mark.asyncio
async def test_repeated_calls_return_findable_results():
    """A repeated request returns a result referencing the original --
    the caller can always trace a duplicate back to what actually happened."""
    executor = SandboxActionExecutor()
    decision = _decision(decision_id="fixed-id-2")
    first = await executor.execute(decision)
    second = await executor.execute(decision)
    assert executor.get(first.action_id) is not None
    assert executor.get(second.action_id).duplicate_of_action_id == first.action_id


# ----------------------------------------------------------------------
# 14-15: No real payment API, simulation flag explicit
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sandbox_result_explicitly_marked_as_simulation():
    executor = SandboxActionExecutor()
    result = await executor.execute(_decision())
    assert result.simulation is True
    assert "SANDBOX SIMULATION" in result.detail
    assert "no real system was contacted" in result.detail.lower()


def test_no_real_payment_client_imported_anywhere_in_actions_module():
    """Static check: nothing under app/actions imports an HTTP client,
    a payment SDK, or anything resembling a real external integration."""
    actions_dir = Path(__file__).resolve().parents[1] / "app" / "actions"
    forbidden_imports = ["import requests", "import httpx", "import stripe", "import razorpay", "urllib.request"]
    for py_file in actions_dir.glob("*.py"):
        content = py_file.read_text()
        for pattern in forbidden_imports:
            assert pattern not in content, f"{py_file.name} imports {pattern!r} -- not sandbox-only"


# ----------------------------------------------------------------------
# 16: Action failure is handled safely
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_executor_failure_does_not_raise_past_the_validator_boundary():
    """A validation failure raises ActionValidationError specifically
    (never a bare/unclassified exception) so callers can distinguish
    'rejected by policy validation' from 'unexpected executor bug'."""
    executor = SandboxActionExecutor()
    with pytest.raises(ActionValidationError):
        await executor.execute(_decision(cluster_id=""))
