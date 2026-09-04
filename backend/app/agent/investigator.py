"""Orchestrates one investigation: calls the Gemini client, validates the
result, and wraps everything into the final `InvestigationResult` --
the M4 output contract, safe to return on any outcome including total
failure.

LOGGING: only cluster ID, status, latency, model identifier, and
validation outcome are logged. Never the API key, the request payload,
or raw Gemini output (which could echo back a malformed/unexpected
string). See `test_no_secrets_in_logs` in tests/test_agent.py.
"""

from __future__ import annotations

import logging

from app.agent.gemini_client import UNAVAILABLE_ERROR_TYPES, GeminiClientInterface
from app.agent.models import InvestigationMetadata, InvestigationRequest, InvestigationResult, InvestigationStatus
from app.agent.validation import InvestigationValidationError, validate_investigation_response

logger = logging.getLogger("trustgraph.agent")


async def investigate(
    request: InvestigationRequest, client: GeminiClientInterface
) -> InvestigationResult:
    """Run one investigation. Never raises -- every failure mode produces
    a valid `InvestigationResult` with an appropriate status instead.
    """
    result = await client.generate_investigation(request)

    if result.error_type is not None:
        status = (
            InvestigationStatus.AI_UNAVAILABLE
            if result.error_type in UNAVAILABLE_ERROR_TYPES
            else InvestigationStatus.INVESTIGATION_FAILED
        )
        logger.warning(
            "investigation failed cluster_id=%s status=%s error_type=%s model=%s latency_ms=%.1f",
            request.cluster_id, status.value, result.error_type.value, result.model, result.latency_ms,
        )
        return InvestigationResult(
            cluster_id=request.cluster_id,
            status=status,
            ml_assessment=request.ml_assessment,
            metadata=InvestigationMetadata(
                model=result.model, latency_ms=result.latency_ms, error=result.error_message
            ),
        )

    try:
        validated = validate_investigation_response(
            result.raw_json, allowed_evidence_refs=set(request.signals.keys())
        )
    except InvestigationValidationError as exc:
        logger.warning(
            "investigation validation failed cluster_id=%s model=%s latency_ms=%.1f",
            request.cluster_id, result.model, result.latency_ms,
        )
        return InvestigationResult(
            cluster_id=request.cluster_id,
            status=InvestigationStatus.INVESTIGATION_FAILED,
            ml_assessment=request.ml_assessment,
            metadata=InvestigationMetadata(
                model=result.model, latency_ms=result.latency_ms, error=str(exc)
            ),
        )

    logger.info(
        "investigation completed cluster_id=%s model=%s latency_ms=%.1f classification=%s",
        request.cluster_id, result.model, result.latency_ms, validated.assessment.classification.value,
    )

    # cluster_id always comes from OUR request, never from Gemini's echoed
    # value -- prevents the AI from silently redirecting an investigation
    # to a different cluster identity even if it echoes back something else.
    return InvestigationResult(
        cluster_id=request.cluster_id,
        status=InvestigationStatus.COMPLETED,
        ml_assessment=request.ml_assessment,
        assessment=validated.assessment,
        summary=validated.summary,
        key_findings=validated.key_findings,
        supporting_evidence=validated.supporting_evidence,
        contradicting_evidence=validated.contradicting_evidence,
        investigation_recommendations=validated.investigation_recommendations,
        recommended_action=validated.recommended_action,
        metadata=InvestigationMetadata(model=result.model, latency_ms=result.latency_ms),
    )
