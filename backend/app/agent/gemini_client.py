"""Gemini client abstraction.

Nothing outside this module calls the Gemini SDK directly --
`investigator.py` only ever talks to a `GeminiClientInterface`, so the
provider is fully isolated and replaceable (and testable without
network access via `MockGeminiClient`).

    Investigator
         |
         v
    GeminiClientInterface
       /        \\
  RealGeminiClient   MockGeminiClient

Neither client ever raises out of `generate_investigation` for
provider-level failures (timeout, auth, rate limit, malformed output,
...) -- they always return a `GeminiRawResult`, with `error_type` set
on failure. This is what lets `investigator.py` handle every failure
mode uniformly and never crash the surrounding application.
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from app.agent.models import InvestigationRequest, InvestigationResponse, RecommendedAction, Severity
from app.agent.prompts import SYSTEM_PROMPT, build_user_content
from app.risk.config import RiskLevel


class GeminiErrorType(str, Enum):
    MISSING_API_KEY = "MISSING_API_KEY"
    AUTH_ERROR = "AUTH_ERROR"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_ERROR = "NETWORK_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    EMPTY_RESPONSE = "EMPTY_RESPONSE"
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"
    UNKNOWN = "UNKNOWN"


# Error types worth retrying (transient); anything else fails fast.
_RETRYABLE_ERRORS = {
    GeminiErrorType.TIMEOUT,
    GeminiErrorType.RATE_LIMITED,
    GeminiErrorType.NETWORK_ERROR,
    GeminiErrorType.PROVIDER_ERROR,
}

# Error types that should map to AI_UNAVAILABLE (provider/connectivity
# problem) rather than INVESTIGATION_FAILED (something about the
# response itself was wrong) in investigator.py.
UNAVAILABLE_ERROR_TYPES = {
    GeminiErrorType.MISSING_API_KEY,
    GeminiErrorType.AUTH_ERROR,
    GeminiErrorType.TIMEOUT,
    GeminiErrorType.RATE_LIMITED,
    GeminiErrorType.NETWORK_ERROR,
    GeminiErrorType.PROVIDER_ERROR,
}


@dataclass(frozen=True)
class GeminiRawResult:
    model: str
    latency_ms: float
    raw_json: dict | None
    error_type: GeminiErrorType | None = None
    error_message: str | None = None


class GeminiClientInterface(ABC):
    @abstractmethod
    async def generate_investigation(self, request: InvestigationRequest) -> GeminiRawResult:
        ...

    async def aclose(self) -> None:
        """Release any underlying network resources (connections, sessions).

        Default no-op -- only `RealGeminiClient` holds anything that
        needs closing. Callers that construct a client via
        `get_default_gemini_client()` for a single request should
        `await client.aclose()` when done; callers that hold a
        long-lived client (or use `MockGeminiClient`) can ignore this.
        """
        return None


# ----------------------------------------------------------------------
# Real client
# ----------------------------------------------------------------------
def _classify_exception(exc: Exception) -> tuple[GeminiErrorType, str]:
    """Best-effort classification of an SDK exception into an error type.

    Uses type/message heuristics rather than importing every possible
    SDK exception class by name -- keeps this resilient to SDK version
    differences. Never includes the API key or request payload in the
    resulting message.
    """
    name = type(exc).__name__.lower()
    message = str(exc).lower()

    if "timeout" in name or "timeout" in message:
        return GeminiErrorType.TIMEOUT, "Request to Gemini timed out."
    if "permission" in message or "unauthorized" in message or "api key not valid" in message or "401" in message or "403" in message:
        return GeminiErrorType.AUTH_ERROR, "Gemini rejected the API key or permissions."
    if "429" in message or "rate limit" in message or "resource_exhausted" in message.replace(" ", "_"):
        return GeminiErrorType.RATE_LIMITED, "Gemini rate limit exceeded."
    if "connection" in message or "network" in name or "dns" in message:
        return GeminiErrorType.NETWORK_ERROR, "Network error reaching Gemini."
    if "500" in message or "502" in message or "503" in message or "internal" in message:
        return GeminiErrorType.PROVIDER_ERROR, "Gemini provider error."
    return GeminiErrorType.UNKNOWN, f"Unexpected error calling Gemini: {type(exc).__name__}"


class RealGeminiClient(GeminiClientInterface):
    """Calls the real Gemini API via the official `google-genai` SDK.

    Retry policy: up to `max_retries` additional attempts (so
    `max_retries=2` means 3 total attempts), ONLY for transient error
    types (timeout, rate limit, network, generic provider error) --
    never for auth errors or missing keys, where retrying cannot help.
    Backoff is a short fixed/exponential delay (capped at 4s) between
    attempts to avoid hammering a struggling provider.
    """

    def __init__(self, api_key: str | None, model: str, timeout_seconds: float, max_retries: int):
        self._api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = None
        if api_key:
            from google import genai

            self._client = genai.Client(api_key=api_key)

    async def generate_investigation(self, request: InvestigationRequest) -> GeminiRawResult:
        start = time.perf_counter()

        if not self._api_key or self._client is None:
            return GeminiRawResult(
                model=self.model,
                latency_ms=(time.perf_counter() - start) * 1000,
                raw_json=None,
                error_type=GeminiErrorType.MISSING_API_KEY,
                error_message="GEMINI_API_KEY is not configured.",
            )

        from google.genai import types

        last_error: tuple[GeminiErrorType, str] | None = None
        attempts = self.max_retries + 1

        for attempt in range(attempts):
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=self.model,
                        contents=build_user_content(request),
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            response_mime_type="application/json",
                            response_schema=InvestigationResponse,
                            temperature=0.2,
                        ),
                    ),
                    timeout=self.timeout_seconds,
                )
                latency_ms = (time.perf_counter() - start) * 1000
                text = getattr(response, "text", None)
                if not text:
                    return GeminiRawResult(
                        model=self.model,
                        latency_ms=latency_ms,
                        raw_json=None,
                        error_type=GeminiErrorType.EMPTY_RESPONSE,
                        error_message="Gemini returned an empty response.",
                    )
                try:
                    raw_json = json.loads(text)
                except json.JSONDecodeError as exc:
                    return GeminiRawResult(
                        model=self.model,
                        latency_ms=latency_ms,
                        raw_json=None,
                        error_type=GeminiErrorType.MALFORMED_OUTPUT,
                        error_message=f"Gemini output was not valid JSON: {exc}",
                    )
                return GeminiRawResult(
                    model=self.model, latency_ms=latency_ms, raw_json=raw_json
                )

            except asyncio.TimeoutError:
                last_error = (GeminiErrorType.TIMEOUT, "Request to Gemini timed out.")
            except Exception as exc:  # noqa: BLE001 -- deliberately broad; classified below
                last_error = _classify_exception(exc)

            if last_error[0] not in _RETRYABLE_ERRORS or attempt == attempts - 1:
                break
            await asyncio.sleep(min(2**attempt, 4))

        latency_ms = (time.perf_counter() - start) * 1000
        error_type, error_message = last_error or (GeminiErrorType.UNKNOWN, "Unknown error.")
        return GeminiRawResult(
            model=self.model,
            latency_ms=latency_ms,
            raw_json=None,
            error_type=error_type,
            error_message=error_message,
        )

    async def aclose(self) -> None:
        """Close the underlying SDK client's network resources, if any."""
        if self._client is not None:
            await self._client.aio.aclose()


# ----------------------------------------------------------------------
# Mock client -- deterministic, no network, no API key required
# ----------------------------------------------------------------------
# Maps M3's combined contributor signal name to the canonical M2 signal
# name(s) it corresponds to, so mock-generated findings reference valid
# evidence keys (M3's "shared_device_and_network" contributor combines
# two of M2's seven canonical signal names into one scoring category).
_CONTRIBUTOR_TO_EVIDENCE_REFS = {
    "shared_device_and_network": ["shared_device", "shared_network"],
    "account_creation_burst": ["account_creation_burst"],
    "transaction_velocity": ["transaction_velocity"],
    "transaction_coordination": ["transaction_coordination"],
    "return_anomaly": ["return_anomaly"],
    "graph_connectivity": ["graph_connectivity"],
}

_RISK_LEVEL_TO_SEVERITY = {
    RiskLevel.LOW: Severity.LOW,
    RiskLevel.MEDIUM: Severity.MEDIUM,
    RiskLevel.HIGH: Severity.HIGH,
    RiskLevel.CRITICAL: Severity.CRITICAL,
}

_RISK_LEVEL_TO_MOCK_ACTION = {
    RiskLevel.LOW: RecommendedAction.NO_ACTION,
    RiskLevel.MEDIUM: RecommendedAction.MONITOR,
    RiskLevel.HIGH: RecommendedAction.REVIEW,
    RiskLevel.CRITICAL: RecommendedAction.HOLD_FOR_REVIEW,
}


class MockGeminiClient(GeminiClientInterface):
    """Deterministic offline investigator used for tests and local development.

    The mock deliberately consumes the same ML assessment contract exposed to
    the real Gemini investigator. It does NOT attempt to imitate LLM reasoning.
    Its purpose is to make the ML -> Investigator integration testable,
    reproducible, and safe without a network call.
    """

    def __init__(self, model: str = "mock-gemini"):
        self.model = model

    async def generate_investigation(
        self,
        request: InvestigationRequest,
    ) -> GeminiRawResult:
        start = time.perf_counter()

        strong = [
            c
            for c in request.contributors
            if c.contribution >= 0.5 * c.max_contribution
        ]

        weak = [
            c
            for c in request.contributors
            if c.contribution < 0.1 * c.max_contribution
        ]

        relationship_only = bool(strong) and all(
            c.signal in (
                "shared_device_and_network",
                "graph_connectivity",
            )
            for c in strong
        )

        ml = request.ml_assessment

        # ---------------------------------------------------------------
        # ML-aware investigative reasoning
        # ---------------------------------------------------------------

        ml_disagreement = bool(ml and ml.disagreement)
        ml_strong = bool(ml and ml.prediction and ml.probability >= 0.75)
        ml_weak = bool(ml and not ml.prediction and ml.probability < 0.25)

        # Behavioral corroboration means the learned model agrees with a
        # suspicious deterministic assessment.
        ml_corroborates_risk = bool(
            ml
            and ml.prediction
            and ml.deterministic_prediction
        )

        # The important case: ML sees strong behavioral evidence while the
        # deterministic operating point has not been crossed.
        ml_detects_hidden_behavior = bool(
            ml
            and ml.prediction
            and not ml.deterministic_prediction
            and ml.probability >= 0.75
        )

        # Deterministic risk remains the safety floor.
        if request.risk.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            classification = "POTENTIAL_COORDINATED_ABUSE"

        elif ml_detects_hidden_behavior:
            classification = "POTENTIAL_COORDINATED_ABUSE"

        elif not strong:
            classification = "NORMAL_ACTIVITY"

        elif relationship_only and not ml_strong:
            classification = "LEGITIMATE_SHARED_INFRASTRUCTURE"

        else:
            classification = "INSUFFICIENT_EVIDENCE"

        # ---------------------------------------------------------------
        # Severity
        # ---------------------------------------------------------------

        severity = _RISK_LEVEL_TO_SEVERITY[request.risk.level].value

        # Base confidence follows deterministic evidence.
        confidence = min(
            0.5 + request.risk.score / 200,
            0.95,
        )

        # ML disagreement adds investigative confidence only when the model
        # strongly disagrees in the suspicious direction.
        if ml_detects_hidden_behavior:
            confidence = min(confidence + 0.10, 0.95)

        elif ml_corroborates_risk:
            confidence = min(confidence + 0.05, 0.95)

        elif ml_weak and request.risk.level in (
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ):
            confidence = max(confidence - 0.05, 0.50)

        confidence = round(confidence, 2)

        # ---------------------------------------------------------------
        # Recommended action
        # ---------------------------------------------------------------

        recommended_action = _RISK_LEVEL_TO_MOCK_ACTION[
            request.risk.level
        ].value

        # ML may strengthen an investigation recommendation, but never
        # bypasses deterministic safety policy.
        if ml_detects_hidden_behavior:
            recommended_action = RecommendedAction.REVIEW.value

        # ---------------------------------------------------------------
        # Findings
        # ---------------------------------------------------------------

        key_findings = [
            {
                "finding": c.evidence,
                "evidence_refs": _CONTRIBUTOR_TO_EVIDENCE_REFS.get(
                    c.signal,
                    [],
                ),
            }
            for c in sorted(
                request.contributors,
                key=lambda c: c.contribution,
                reverse=True,
            )[:3]
            if c.contribution > 0
        ]

        # Add an explicit ML finding for disagreement/corroboration.
        if ml is not None and ml.disagreement:
            direction = (
                "behavioral model flags the cluster"
                if ml.prediction
                else "behavioral model does not flag the cluster"
            )

            key_findings.append(
                {
                    "finding": (
                        f"Detector/ML disagreement: deterministic prediction="
                        f"{ml.deterministic_prediction}, ML prediction="
                        f"{ml.prediction}, ML behavioral score="
                        f"{ml.probability:.4f}; {direction}. "
                        "The disagreement is treated as secondary investigative "
                        "evidence and does not override deterministic risk."
                    ),
                    "evidence_refs": [],
                }
            )

        supporting_evidence = [
            c.evidence
            for c in strong
        ]

        contradicting_evidence = [
            (
                f"{c.signal} contributed minimally "
                f"({c.contribution}/{c.max_contribution}): {c.evidence}"
            )
            for c in weak
        ]

        if ml_detects_hidden_behavior:
            supporting_evidence.append(
                (
                    f"Behavioral ML assessment flags the cluster with score "
                    f"{ml.probability:.4f}, despite deterministic risk remaining "
                    f"below the configured operating threshold."
                )
            )

        elif ml is not None and ml.disagreement:
            contradicting_evidence.append(
                (
                    f"Detector/ML disagreement is present "
                    f"(ML score={ml.probability:.4f}); the model output is "
                    "secondary evidence rather than enforcement authority."
                )
            )

        # ---------------------------------------------------------------
        # Recommendations
        # ---------------------------------------------------------------

        recommendations_by_classification = {
            "NORMAL_ACTIVITY": [
                "No further investigation indicated beyond standard monitoring.",
            ],
            "LEGITIMATE_SHARED_INFRASTRUCTURE": [
                "Confirm shared device/network usage is consistent with a "
                "household or office pattern.",
                "No elevated action indicated based on current evidence.",
            ],
            "POTENTIAL_COORDINATED_ABUSE": [
                "Manually review shared-device/network membership for legitimacy.",
                "Cross-check account creation timestamps against known "
                "onboarding campaigns.",
                "Verify return concentration against customer support records.",
            ],
            "INSUFFICIENT_EVIDENCE": [
                "Gather additional behavioral history before drawing a conclusion.",
            ],
        }

        if ml_detects_hidden_behavior:
            recommendations_by_classification[
                "POTENTIAL_COORDINATED_ABUSE"
            ].append(
                "Investigate the detector/ML disagreement and identify which "
                "behavioral signals are driving the learned model."
            )

        # ---------------------------------------------------------------
        # Summary
        # ---------------------------------------------------------------

        summary_parts = [
            f"[MOCK] Cluster {request.cluster_id}: risk score "
            f"{request.risk.score} ({request.risk.level.value})"
        ]

        if strong:
            summary_parts.append(
                f"{len(strong)} strong evidence "
                f"categor{'y' if len(strong) == 1 else 'ies'}"
            )

        if ml is not None:
            summary_parts.append(
                f"ML behavioral score {ml.probability:.4f}"
            )

            if ml.disagreement:
                summary_parts.append(
                    "detector/ML disagreement requires investigation"
                )
            elif ml_corroborates_risk:
                summary_parts.append(
                    "ML corroborates the deterministic assessment"
                )

        summary = "; ".join(summary_parts) + (
            f". Classified as {classification}."
        )

        raw_json = {
            "cluster_id": request.cluster_id,
            "assessment": {
                "classification": classification,
                "severity": severity,
                "confidence": confidence,
            },
            "summary": summary,
            "key_findings": key_findings,
            "supporting_evidence": supporting_evidence,
            "contradicting_evidence": contradicting_evidence,
            "investigation_recommendations": (
                recommendations_by_classification[classification]
            ),
            "recommended_action": recommended_action,
        }

        latency_ms = (time.perf_counter() - start) * 1000

        return GeminiRawResult(
            model=self.model,
            latency_ms=latency_ms,
            raw_json=raw_json,
        )