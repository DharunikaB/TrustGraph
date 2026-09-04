"""Append-only audit service.

In-memory for M5 (same "simplest architecture that doesn't block a
future DB table" reasoning as `PolicyDecisionStore` and
`SandboxActionExecutor`'s stores) -- `AuditEvent` is already a frozen
Pydantic model, so backing this with a real table later is a storage
change, not a contract change.

FAIL-SAFE CONTRACT: `record()` can raise (e.g. if a future persistent
backend is unreachable). Callers that are about to report an action as
successfully executed MUST catch that and downgrade the result -- see
`app/workflow.py`'s `_execute_action_with_audit`, which is exactly the
"if audit recording fails, do not silently claim the action
succeeded" requirement from the spec, implemented and tested.
"""

from __future__ import annotations

from app.audit.models import AuditEvent, AuditEventType


class AuditService:
    def __init__(self):
        self._events: list[AuditEvent] = []

    def record(
        self,
        event_type: AuditEventType,
        cluster_id: str,
        investigation_id: str | None = None,
        decision_id: str | None = None,
        action_id: str | None = None,
        previous_state: str | None = None,
        new_state: str | None = None,
        reason_codes: list[str] | None = None,
        policy_version: str | None = None,
        execution_status: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            cluster_id=cluster_id,
            investigation_id=investigation_id,
            decision_id=decision_id,
            action_id=action_id,
            previous_state=previous_state,
            new_state=new_state,
            reason_codes=reason_codes or [],
            policy_version=policy_version,
            execution_status=execution_status,
        )
        self._events.append(event)
        return event

    def get_for_cluster(self, cluster_id: str) -> list[AuditEvent]:
        return [e for e in self._events if e.cluster_id == cluster_id]

    def get_by_id(self, audit_id: str) -> AuditEvent | None:
        return next((e for e in self._events if e.audit_id == audit_id), None)

    def clear(self) -> None:
        self._events.clear()


# Module-level singleton -- must be shared across requests so
# GET /audit/{cluster_id} can see events recorded by earlier
# POST /agent/respond/{cluster_id} calls within the same process.
audit_service = AuditService()
