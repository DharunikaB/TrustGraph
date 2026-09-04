"""Pydantic contracts for the M4 AI Investigator.

Two contracts matter here:

- `InvestigationRequest`: what we send TO Gemini. Reuses M3's actual
  Pydantic types (`Contributor`, `ExposureAssessment`, `RiskLevel`)
  directly rather than redefining parallel schemas with the same
  fields under different names -- the spec is explicit that this must
  be the exact M3 output, not an invented duplicate.

- `InvestigationResponse`: the strict schema Gemini's structured
  output must validate against. Nothing free-form is ever parsed with
  string scraping; a response that doesn't fit this schema is a failed
  investigation, not a best-effort guess.

`InvestigationResult` is the final M4 output contract (what the API
returns) -- a superset of `InvestigationResponse` with status/metadata
wrapped around it, safe to return even when Gemini failed entirely.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.risk.config import RiskLevel
from app.risk.models import Contributor, ExposureAssessment


# ----------------------------------------------------------------------
# Enums -- deliberately closed vocabularies. Gemini cannot invent new
# values; a value outside these sets fails Pydantic validation and the
# investigation is treated as failed, never silently accepted.
# ----------------------------------------------------------------------
class Classification(str, Enum):
    NORMAL_ACTIVITY = "NORMAL_ACTIVITY"
    LEGITIMATE_SHARED_INFRASTRUCTURE = "LEGITIMATE_SHARED_INFRASTRUCTURE"
    POTENTIAL_COORDINATED_ABUSE = "POTENTIAL_COORDINATED_ABUSE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Severity(str, Enum):
    """Gemini's own qualitative read of the evidence.

    Deliberately a SEPARATE concept from `risk.level` (M3's
    deterministic score-derived band, already present in the context
    sent to Gemini). The two may agree or disagree -- disagreement is
    useful signal, not an error, and nothing here ever overwrites
    `risk.level`.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecommendedAction(str, Enum):
    """Bounded operational categories only -- never an executable instruction.

    M5's Policy Engine interprets these later; nothing here is a
    command ("block customer X", "refund transaction Y") and the
    validation layer rejects any response that isn't one of these
    exact enum values.
    """

    NO_ACTION = "NO_ACTION"
    MONITOR = "MONITOR"
    REVIEW = "REVIEW"
    HOLD_FOR_REVIEW = "HOLD_FOR_REVIEW"
    ESCALATE = "ESCALATE"


class InvestigationStatus(str, Enum):
    COMPLETED = "COMPLETED"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    INVESTIGATION_FAILED = "INVESTIGATION_FAILED"


# ----------------------------------------------------------------------
# Request (M3 evidence -> Gemini), minimized
# ----------------------------------------------------------------------
class EntityCounts(BaseModel):
    """Aggregate counts only -- never the underlying ID lists.

    Gemini needs to know "12 customers, 3 devices" to reason about
    scale; it does not need the 12 customer UUIDs to do that, so they
    are never included. See context.py's data-minimization docstring.
    """

    model_config = ConfigDict(frozen=True)

    customer_count: int = Field(ge=0)
    device_count: int = Field(ge=0)
    network_count: int = Field(ge=0)
    transaction_count: int = Field(ge=0)


class RiskContext(BaseModel):
    """M3's deterministic risk assessment -- read-only context for Gemini.

    Deliberately excludes `contributors` here (those are sent
    separately, unchanged, at the top level of `InvestigationRequest`)
    to match the M3 output shape exactly rather than nesting it twice.
    """

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=100)
    level: RiskLevel


class MLAssessment(BaseModel):
    """Secondary behavioral-model assessment supplied to Gemini.

    This is an independent behavioral signal. It does not modify M3's
    deterministic risk score and is not a calibrated fraud probability.
    """

    model_config = ConfigDict(frozen=True)

    probability: float = Field(
        ge=0,
        le=1,
        description=(
            "Behavioral model score. This is not a calibrated real-world "
            "fraud probability."
        ),
    )
    prediction: bool
    deterministic_prediction: bool
    disagreement: bool

class InvestigationRequest(BaseModel):
    """Everything sent to Gemini for one candidate cluster. Nothing more."""

    model_config = ConfigDict(frozen=True)

    cluster_id: str
    entities: EntityCounts
    risk: RiskContext
    exposure: ExposureAssessment
    signals: dict = Field(
        description="M2's signals dict, with internal device/network ID-keyed "
        "breakdowns stripped -- see context.py's sanitize_signals_for_agent."
    )
    contributors: list[Contributor]
    evidence: list[str]
    ml_assessment: MLAssessment | None = None


# ----------------------------------------------------------------------
# Response (Gemini -> validated structured output)
# ----------------------------------------------------------------------
class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    finding: str = Field(min_length=1)
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="Must be a subset of the signal names present in the "
        "request that was sent (validated in validation.py, not by Pydantic "
        "alone, since the allowed set is request-dependent).",
    )


class Assessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    classification: Classification
    severity: Severity
    confidence: float = Field(
        ge=0,
        le=1,
        description="Gemini's confidence in ITS OWN interpretation -- "
        "distinct from and never combined with M3's risk.score.",
    )


class InvestigationResponse(BaseModel):
    """The strict schema Gemini's structured output must validate against."""

    model_config = ConfigDict(frozen=True)

    cluster_id: str
    assessment: Assessment
    summary: str = Field(min_length=1, max_length=2000)
    key_findings: list[Finding] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    investigation_recommendations: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction


# ----------------------------------------------------------------------
# Final M4 output contract -- what the API returns, always, even on failure
# ----------------------------------------------------------------------
class InvestigationMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    latency_ms: float = Field(ge=0)
    error: str | None = None


class InvestigationResult(BaseModel):
    """The M5 input contract. Safe to return on any status, including failure."""

    model_config = ConfigDict(frozen=True)

    investigation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cluster_id: str
    status: InvestigationStatus
    ml_assessment: MLAssessment | None = None

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    assessment: Assessment | None = None
    summary: str | None = None
    key_findings: list[Finding] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    investigation_recommendations: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction | None = None

    metadata: InvestigationMetadata
