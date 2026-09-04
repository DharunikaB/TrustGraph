"""The ONLY action executor implementation in this project.

SANDBOX / SIMULATION ONLY. `SandboxActionExecutor` never calls a real
payment API, never contacts a real customer account, never mutates any
financial record, never sends a real notification, and never invokes
any external system of any kind. Every `ActionResult` it produces has
`simulation=True`, unconditionally -- there is no configuration flag,
environment variable, or code path anywhere in this class that can
change that. This is the concrete demonstration of the spec's
non-negotiable requirement: "This implementation does not execute real
payment/customer actions."

IDEMPOTENCY: keyed on (decision_id, action_type, cluster_id). Calling
`execute()` twice with the same `PolicyDecision` returns a NEW
`ActionResult` with `status=DUPLICATE` and `duplicate_of_action_id`
pointing at the original -- the original result is never mutated, and
no second "effective" action is recorded. This directly implements the
spec's idempotency requirement: the same decision processed twice
(e.g. a retried request) never produces two independent simulated
effects.
"""

from __future__ import annotations

from app.actions.executor import ActionExecutorInterface, ActionValidator
from app.actions.models import ActionResult, ActionStatus, ActionTarget
from app.policy.models import PolicyDecision


def _idempotency_key(decision: PolicyDecision) -> str:
    return f"{decision.decision_id}:{decision.decision.value}:{decision.cluster_id}"


class SandboxActionExecutor(ActionExecutorInterface):
    def __init__(self, validator: ActionValidator | None = None):
        self._validator = validator or ActionValidator()
        self._by_idempotency_key: dict[str, ActionResult] = {}
        self._by_action_id: dict[str, ActionResult] = {}

    async def execute(self, decision: PolicyDecision) -> ActionResult:
        # Raises ActionValidationError on any doubt -- caller (workflow.py)
        # catches it and records ActionResult(status=REJECTED). This
        # method never swallows a validation failure into a "successful"
        # result.
        self._validator.validate(decision)

        key = _idempotency_key(decision)
        existing = self._by_idempotency_key.get(key)
        if existing is not None:
            duplicate = ActionResult(
                action_type=decision.decision,
                target=ActionTarget(cluster_id=decision.cluster_id),
                decision_id=decision.decision_id,
                status=ActionStatus.DUPLICATE,
                detail=(
                    f"This decision ({decision.decision_id}) already produced an effective "
                    f"action ({existing.action_id}); no new sandbox effect was simulated."
                ),
                duplicate_of_action_id=existing.action_id,
            )
            self._by_action_id[duplicate.action_id] = duplicate
            return duplicate

        result = ActionResult(
            action_type=decision.decision,
            target=ActionTarget(cluster_id=decision.cluster_id),
            decision_id=decision.decision_id,
            status=ActionStatus.SIMULATED,
            detail=(
                f"[SANDBOX SIMULATION -- no real system was contacted] "
                f"Simulated {decision.decision.value} for cluster {decision.cluster_id}."
            ),
        )
        self._by_idempotency_key[key] = result
        self._by_action_id[result.action_id] = result
        return result

    def get(self, action_id: str) -> ActionResult | None:
        return self._by_action_id.get(action_id)

    def clear(self) -> None:
        self._by_idempotency_key.clear()
        self._by_action_id.clear()


# Module-level singleton -- see PolicyDecisionStore's docstring in
# app/policy/engine.py for the same "simplest architecture for now"
# reasoning. Provides both the idempotency guarantee (must be shared
# across requests to actually prevent duplicate effective actions) and
# GET /actions/{action_id} lookups.
sandbox_executor = SandboxActionExecutor()
