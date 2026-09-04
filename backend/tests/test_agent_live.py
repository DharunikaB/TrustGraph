"""Live Gemini integration test -- SEPARATE from the mandatory test suite.

Per the M4 spec: live Gemini calls must never be part of the mandatory
unit test suite, and a missing API key must be reported as skipped,
never as a failure. `pytest.mark.skipif` achieves exactly that: this
test is auto-skipped (not failed) whenever `GEMINI_API_KEY` isn't set
in the environment, so `pytest` (the full suite, including this file)
passes cleanly with zero live API access, and this test only actually
exercises the network when a real key is present and a developer
explicitly wants to verify live integration.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.agent.context import build_investigation_context
from app.agent.gemini_client import RealGeminiClient
from app.agent.investigator import investigate
from app.agent.models import InvestigationStatus
from app.core.config import get_settings
from app.intelligence.pipeline import run_pipeline
from app.risk.pipeline import score_clusters
from tests.test_intelligence import _suspicious_coordinated_scenario

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


@pytest.mark.skipif(
    not GEMINI_API_KEY,
    reason="Live Gemini integration test skipped -- GEMINI_API_KEY not configured.",
)
@pytest.mark.asyncio
async def test_live_gemini_investigation():
    """One real request to Gemini, using a known, hand-built investigation
    context (the same suspicious-coordinated-cluster scenario used
    throughout M2/M3/M4's offline tests). Validates the response passes
    the same strict Pydantic schema the mock client's output does, and
    prints timing/model info without ever printing the API key.
    """
    settings = get_settings()
    data, _ = _suspicious_coordinated_scenario()
    scored = score_clusters(run_pipeline(data), data)
    request = build_investigation_context(scored[0])

    client = RealGeminiClient(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
        timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
        max_retries=settings.GEMINI_MAX_RETRIES,
    )

    start = time.perf_counter()
    result = await investigate(request, client)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"\nLive Gemini test -- model={settings.GEMINI_MODEL} "
          f"status={result.status.value} latency={elapsed_ms:.0f}ms")

    assert result.status in (InvestigationStatus.COMPLETED, InvestigationStatus.AI_UNAVAILABLE)

    if result.status == InvestigationStatus.COMPLETED:
        assert result.assessment is not None
        assert 0 <= result.assessment.confidence <= 1
        assert result.recommended_action is not None
        assert result.summary
        print(f"classification={result.assessment.classification.value} "
              f"confidence={result.assessment.confidence}")
    else:
        # A live-but-unavailable outcome (rate limit, transient network
        # issue) is acceptable for this smoke test -- it's not asserting
        # Gemini is always reachable, only that OUR handling is correct
        # when it is.
        print(f"Gemini was unavailable during this run: {result.metadata.error}")
