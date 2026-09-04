"""Action executor interface and the fail-closed validator every action
must pass through before execution.

    PolicyDecision
        |
        v
    ActionValidator.validate()   -- raises ActionValidationError on ANY doubt
        |
        v
    ActionExecutorInterface.execute()
        |
        v
    ActionResult

FAIL-CLOSED PRINCIPLE: `validate()` raises rather than returning a
boolean. The caller (see `app/workflow.py`) treats any raised
exception as "do not execute" and records `ActionResult(status=REJECTED)`
-- there is no code path where an unvalidated or partially-valid
decision reaches an executor.

Nothing here ever interprets Gemini-generated text as an instruction.
The ONLY thing validated is the `PolicyDecision` object itself -- a
value produced entirely by the deterministic `PolicyEngine` in
`app/policy/engine.py`. `PolicyDecision.decision` is a closed Pydantic
enum (`ActionType`), so "arbitrary action strings", "shell commands",
and "URLs" are structurally impossible values for it to hold in the
first place; validation here is defense in depth (confirming the
decision is internally consistent), not a defense against raw text
that could never reach this far.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.actions.models import ActionResult, ActionType
from app.policy.models import PolicyDecision


class ActionValidationError(Exception):
    """Raised when a PolicyDecision cannot be safely turned into an action."""


class ActionValidator:
    def validate(self, decision: PolicyDecision) -> None:
        if not decision.cluster_id or not decision.cluster_id.strip():
            raise ActionValidationError("PolicyDecision has no target cluster_id.")

        if not decision.decision_id:
            raise ActionValidationError("PolicyDecision has no decision_id to reference.")

        # decision.decision is already a Pydantic-enforced ActionType
        # member (Pydantic would have rejected construction otherwise),
        # but re-check explicitly rather than trusting that upstream
        # code always will -- this is the one place that MUST refuse
        # anything outside the closed set, unconditionally.
        if decision.decision not in set(ActionType):
            raise ActionValidationError(
                f"Decision type {decision.decision!r} is not in the allowed action taxonomy."
            )


class ActionExecutorInterface(ABC):
    @abstractmethod
    async def execute(self, decision: PolicyDecision) -> ActionResult:
        ...
