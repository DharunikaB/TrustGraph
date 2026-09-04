"""Validates raw Gemini output against the strict `InvestigationResponse` schema.

Two layers of validation:

1. Pydantic schema validation -- structure, types, enum membership.
   A response with an invalid `recommended_action` value, a
   `confidence` outside [0, 1], or a missing required field fails here.
2. Evidence-grounding validation -- every `evidence_refs` entry in
   every finding must be one of the signal names actually present in
   the request that was sent. This can't be expressed as a static
   Pydantic constraint since the allowed set depends on the request,
   so it's checked explicitly here.

Either failure raises `InvestigationValidationError`, which
`investigator.py` catches to produce a controlled `INVESTIGATION_FAILED`
result -- never a fabricated one.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.agent.models import InvestigationResponse


class InvestigationValidationError(Exception):
    """Raised when Gemini's output fails schema or evidence-grounding validation."""


def validate_investigation_response(
    raw: dict, allowed_evidence_refs: set[str]
) -> InvestigationResponse:
    """Validate a raw dict (already JSON-parsed) from Gemini.

    `allowed_evidence_refs` should be the set of signal names present
    in the `InvestigationRequest.signals` dict that was actually sent
    -- i.e. what a finding could legitimately be grounded in.
    """
    try:
        response = InvestigationResponse.model_validate(raw)
    except ValidationError as exc:
        raise InvestigationValidationError(f"Schema validation failed: {exc}") from exc

    invalid_refs: list[str] = []
    for finding in response.key_findings:
        for ref in finding.evidence_refs:
            if ref not in allowed_evidence_refs:
                invalid_refs.append(ref)

    if invalid_refs:
        raise InvestigationValidationError(
            f"Finding(s) reference evidence not present in the supplied signals: "
            f"{sorted(set(invalid_refs))}. Allowed: {sorted(allowed_evidence_refs)}."
        )

    return response
