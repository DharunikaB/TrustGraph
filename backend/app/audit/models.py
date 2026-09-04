"""Pydantic contracts for the M5 audit trail.

`AuditEventType` is a closed enum -- exactly the nine event types the
spec names, no free-form event strings anywhere in the codebase.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AuditEventType(str, Enum):
    INVESTIGATION_RECEIVED = "INVESTIGATION_RECEIVED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    DECISION_CREATED = "DECISION_CREATED"
    ACTION_REQUESTED = "ACTION_REQUESTED"
    ACTION_EXECUTED = "ACTION_EXECUTED"
    ACTION_REJECTED = "ACTION_REJECTED"
    ACTION_DUPLICATE = "ACTION_DUPLICATE"
    ACTION_FAILED = "ACTION_FAILED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class AuditEvent(BaseModel):
    """One immutable record in the audit trail.

    Deliberately narrow: only IDs, enum-valued state, reason codes, and
    a policy version ever get recorded -- never raw evidence text, PII,
    or secrets. `previous_state`/`new_state` are short enum-value-shaped
    strings (e.g. a decision or status value), not free-form dumps of
    entire objects.
    """

    model_config = ConfigDict(frozen=True)

    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: AuditEventType

    investigation_id: str | None = None
    cluster_id: str
    decision_id: str | None = None
    action_id: str | None = None

    previous_state: str | None = None
    new_state: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    policy_version: str | None = None

    execution_status: str | None = None
    simulation: bool = True

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
