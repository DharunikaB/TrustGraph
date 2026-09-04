"""Pydantic contracts for M5's bounded action taxonomy.

`ActionType` reuses the SAME enum as `PolicyDecision.decision` (which
itself reuses M4's `RecommendedAction` -- see `app.policy.models` for
the full reasoning). A PolicyDecision authorizes exactly one action of
the matching type; there is no separate "ActionRequest" object,
because the PolicyDecision itself already carries everything an action
needs (type, target cluster, decision reference) -- introducing a
parallel request object would just be a second copy of the same three
fields to keep in sync.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.policy.models import PolicyDecisionType as ActionType

__all__ = ["ActionType", "ActionStatus", "ActionTarget", "ActionResult"]


class ActionStatus(str, Enum):
    SIMULATED = "SIMULATED"
    DUPLICATE = "DUPLICATE"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ActionTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    cluster_id: str


class ActionResult(BaseModel):
    """The outcome of one action-execution attempt.

    `simulation` is always `True` -- there is no code path in this
    project that can set it to `False`. See `sandbox.py`'s module
    docstring: `SandboxActionExecutor` is the ONLY executor
    implementation, and it never contacts a real system.
    """

    model_config = ConfigDict(frozen=True)

    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_type: ActionType
    target: ActionTarget
    decision_id: str

    status: ActionStatus
    simulation: bool = True
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    detail: str
    duplicate_of_action_id: str | None = None
