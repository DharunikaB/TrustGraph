"""M5 orchestration: ties M4's investigation to policy, action, and audit.

    ScoredCluster (found once, reused -- M2/M3 never rerun)
        |
        v
    investigate_scored_cluster()          M4, unchanged
        |
        v
    PolicyEngine.evaluate()                 M5 policy
        |
        v
    ActionValidator -> SandboxActionExecutor  M5 action (fail-closed)
        |
        v
    AuditService.record() at each step         M5 audit
        |
        v
    WorkflowResult

Per the spec's "do not rerun everything unnecessarily" requirement,
this module calls `run_risk_pipeline_async` (M2+M3) exactly ONCE to
locate the target `ScoredCluster`, then reuses M4's
`investigate_scored_cluster(cluster, ...)` interface directly -- there
is no second M2/M3 run hiding inside the M4 or M5 steps.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions.executor import ActionValidationError
from app.actions.models import ActionResult, ActionStatus, ActionTarget
from app.actions.sandbox import SandboxActionExecutor, sandbox_executor
from app.agent.gemini_client import GeminiClientInterface
from app.agent.models import InvestigationResult
from app.agent.pipeline import investigate_scored_cluster
from app.audit.models import AuditEventType
from app.audit.service import AuditService, audit_service
from app.policy.config import PolicyConfig
from app.policy.engine import PolicyDecisionStore, PolicyEngine, policy_decision_store
from app.policy.models import PolicyDecision
from app.risk.pipeline import run_risk_pipeline_async


class WorkflowTiming(BaseModel):
    model_config = ConfigDict(frozen=True)

    investigation_ms: float
    policy_ms: float
    action_ms: float
    total_ms: float


class WorkflowResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cluster_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    investigation: InvestigationResult
    policy_decision: PolicyDecision
    action: ActionResult
    audit_ids: list[str]
    timing: WorkflowTiming


async def _execute_action_with_audit(
    decision: PolicyDecision, executor: SandboxActionExecutor, audit: AuditService
) -> tuple[ActionResult, list[str]]:
    """Run the action through the fail-closed validator/executor, then
    audit it -- with the fail-safe guarantee that an audit-recording
    failure downgrades the reported result rather than silently
    reporting success.
    """
    audit_ids: list[str] = []
    audit_ids.append(
        audit.record(
            AuditEventType.ACTION_REQUESTED,
            cluster_id=decision.cluster_id,
            decision_id=decision.decision_id,
            new_state=decision.decision.value,
            policy_version=decision.policy_version,
        ).audit_id
    )

    try:
        result = await executor.execute(decision)
    except ActionValidationError as exc:
        rejected = ActionResult(
            action_type=decision.decision,
            target=ActionTarget(cluster_id=decision.cluster_id),
            decision_id=decision.decision_id,
            status=ActionStatus.REJECTED,
            detail=f"Action rejected by validator: {exc}",
        )
        try:
            audit_ids.append(
                audit.record(
                    AuditEventType.ACTION_REJECTED,
                    cluster_id=decision.cluster_id,
                    decision_id=decision.decision_id,
                    action_id=rejected.action_id,
                    new_state=ActionStatus.REJECTED.value,
                    execution_status=str(exc),
                    policy_version=decision.policy_version,
                ).audit_id
            )
        except Exception:
            pass  # a rejection's audit failing doesn't change that nothing was executed
        return rejected, audit_ids
    except Exception as exc:  # noqa: BLE001 -- executor failure, not a validation rejection
        failed = ActionResult(
            action_type=decision.decision,
            target=ActionTarget(cluster_id=decision.cluster_id),
            decision_id=decision.decision_id,
            status=ActionStatus.FAILED,
            detail=f"Action executor raised an unexpected error: {exc}",
        )
        try:
            audit_ids.append(
                audit.record(
                    AuditEventType.ACTION_FAILED,
                    cluster_id=decision.cluster_id,
                    decision_id=decision.decision_id,
                    action_id=failed.action_id,
                    new_state=ActionStatus.FAILED.value,
                    policy_version=decision.policy_version,
                ).audit_id
            )
        except Exception:
            pass
        return failed, audit_ids

    # Action executed (SIMULATED or DUPLICATE) -- audit recording MUST
    # succeed for us to report that success. This is the concrete
    # implementation of "if audit recording fails, do not silently
    # claim that an autonomous action completed successfully."
    event_type = (
        AuditEventType.ACTION_EXECUTED
        if result.status == ActionStatus.SIMULATED
        else AuditEventType.ACTION_DUPLICATE
    )
    try:
        audit_ids.append(
            audit.record(
                event_type,
                cluster_id=decision.cluster_id,
                decision_id=decision.decision_id,
                action_id=result.action_id,
                new_state=result.status.value,
                policy_version=decision.policy_version,
            ).audit_id
        )
    except Exception as audit_exc:
        result = ActionResult(
            action_id=result.action_id,
            action_type=result.action_type,
            target=result.target,
            decision_id=result.decision_id,
            status=ActionStatus.FAILED,
            detail=(
                f"Action was simulated (status would have been {result.status.value}) but "
                f"audit recording failed ({audit_exc}); reporting FAILED rather than "
                f"claiming success without a reliable audit trail."
            ),
        )

    return result, audit_ids


async def respond_to_cluster(
    cluster_id: str,
    session: AsyncSession,
    gemini_client: GeminiClientInterface | None = None,
    policy_config: PolicyConfig | None = None,
    executor: SandboxActionExecutor | None = None,
    audit: AuditService | None = None,
    decision_store: PolicyDecisionStore | None = None,
) -> WorkflowResult | None:
    """Run the complete CONNECT->DETECT->SCORE->INVESTIGATE->DECIDE->ACT->AUDIT
    workflow for one cluster. Returns None if `cluster_id` doesn't exist
    in the current M2+M3 run (caller turns this into a 404-shaped response).

    All stateful collaborators (executor/audit/decision_store) default
    to the shared module-level singletons but can be injected -- tests
    use fresh instances so runs don't leak state between each other.
    """
    executor = executor or sandbox_executor
    audit = audit or audit_service
    decision_store = decision_store or policy_decision_store

    total_start = time.perf_counter()

    scored = await run_risk_pipeline_async(session)  # M2+M3, run exactly once
    cluster = next((c for c in scored if c.cluster_id == cluster_id), None)
    if cluster is None:
        return None

    invest_start = time.perf_counter()
    investigation = await investigate_scored_cluster(cluster, gemini_client)
    investigation_ms = (time.perf_counter() - invest_start) * 1000

    audit_ids: list[str] = [
        audit.record(
            AuditEventType.INVESTIGATION_RECEIVED,
            cluster_id=cluster_id,
            investigation_id=investigation.investigation_id,
            new_state=investigation.status.value,
        ).audit_id
    ]

    policy_start = time.perf_counter()
    engine = PolicyEngine(policy_config)
    decision = engine.evaluate(cluster, investigation)
    policy_ms = (time.perf_counter() - policy_start) * 1000

    decision_store.save(decision)
    audit_ids.append(
        audit.record(
            AuditEventType.POLICY_EVALUATED,
            cluster_id=cluster_id,
            investigation_id=investigation.investigation_id,
            decision_id=decision.decision_id,
            new_state=decision.decision.value,
            reason_codes=[r.value for r in decision.reason_codes],
            policy_version=decision.policy_version,
        ).audit_id
    )
    audit_ids.append(
        audit.record(
            AuditEventType.DECISION_CREATED,
            cluster_id=cluster_id,
            investigation_id=investigation.investigation_id,
            decision_id=decision.decision_id,
            new_state=decision.decision.value,
            policy_version=decision.policy_version,
        ).audit_id
    )
    if decision.requires_human_review:
        audit_ids.append(
            audit.record(
                AuditEventType.HUMAN_REVIEW_REQUIRED,
                cluster_id=cluster_id,
                investigation_id=investigation.investigation_id,
                decision_id=decision.decision_id,
                new_state=decision.decision.value,
                policy_version=decision.policy_version,
            ).audit_id
        )

    action_start = time.perf_counter()
    action_result, action_audit_ids = await _execute_action_with_audit(decision, executor, audit)
    action_ms = (time.perf_counter() - action_start) * 1000
    audit_ids.extend(action_audit_ids)

    total_ms = (time.perf_counter() - total_start) * 1000

    return WorkflowResult(
        cluster_id=cluster_id,
        investigation=investigation,
        policy_decision=decision,
        action=action_result,
        audit_ids=audit_ids,
        timing=WorkflowTiming(
            investigation_ms=investigation_ms,
            policy_ms=policy_ms,
            action_ms=action_ms,
            total_ms=total_ms,
        ),
    )
