"""M4 pipeline: find a scored cluster, build its context, investigate it.

    cluster_id
        |
        v
    M2 + M3 (run_risk_pipeline_async)  -- find the matching ScoredCluster
        |
        v
    context.build_investigation_context  -- minimize, wrap in InvestigationRequest
        |
        v
    investigator.investigate  -- call Gemini (real or mock), validate
        |
        v
    InvestigationResult
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import build_investigation_context
from app.agent.gemini_client import GeminiClientInterface, MockGeminiClient, RealGeminiClient
from app.agent.investigator import investigate
from app.agent.models import (
    InvestigationMetadata,
    InvestigationResult,
    InvestigationStatus,
    MLAssessment,
)
from app.core.config import Settings, get_settings
from app.risk.config import RiskConfig
from app.risk.models import ScoredCluster
from app.risk.pipeline import run_risk_pipeline_async
from app.ml.service import MLService

def get_default_gemini_client(settings: Settings | None = None) -> GeminiClientInterface:
    """Real client if a Gemini API key is configured, mock otherwise.

    This is the ONLY place that decides which client to use by
    default -- callers (the API layer) go through this; tests
    construct `MockGeminiClient` directly and never rely on this
    fallback, so test behavior never depends on environment state.
    """
    settings = settings or get_settings()
    if settings.GEMINI_API_KEY:
        return RealGeminiClient(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
            max_retries=settings.GEMINI_MAX_RETRIES,
        )
    return MockGeminiClient()

def get_ml_assessment(cluster: ScoredCluster) -> MLAssessment | None:
    """Run ML as a secondary behavioral signal.

    ML failures never block investigation and never modify deterministic
    TrustGraph risk.
    """

    try:
        assessment = MLService().assess(cluster)

        return MLAssessment(
            probability=assessment.probability,
            prediction=assessment.prediction,
            deterministic_prediction=assessment.deterministic_prediction,
            disagreement=assessment.disagreement,
        )
    except Exception:
        # ML is an enrichment layer, not a safety-critical dependency.
        return None

async def investigate_cluster(
    cluster_id: str,
    session: AsyncSession,
    client: GeminiClientInterface | None = None,
    risk_config: RiskConfig | None = None,
) -> InvestigationResult | None:
    """Find `cluster_id` among the current M2+M3 output and investigate it.

    Returns None if no candidate cluster with that ID exists in the
    current run (the API layer turns this into a 404-shaped response).
    """
    owns_client = client is None
    client = client or get_default_gemini_client()

    try:
        scored = await run_risk_pipeline_async(session, risk_config=risk_config)
        cluster = next((c for c in scored if c.cluster_id == cluster_id), None)
        if cluster is None:
            return None
        ml_assessment = get_ml_assessment(cluster)
        request = build_investigation_context(
            cluster,
            ml_assessment=ml_assessment,
        )
        
        return await investigate(request, client)
    finally:
        # Only close a client we constructed ourselves via the default
        # factory -- a caller-supplied client (tests, batch callers with
        # a long-lived client) owns its own lifecycle.
        if owns_client:
            await client.aclose()


async def investigate_scored_cluster(
    cluster: ScoredCluster, client: GeminiClientInterface | None = None
) -> InvestigationResult:
    """Investigate an already-scored cluster directly (no DB lookup).

    Used by tests and by any caller that already has a `ScoredCluster`
    in hand (e.g. batch investigation of a full M3 run).
    """
    owns_client = client is None
    client = client or get_default_gemini_client()
    try:
        ml_assessment = get_ml_assessment(cluster)
        request = build_investigation_context(cluster, ml_assessment=ml_assessment,)
        return await investigate(request, client)
    finally:
        if owns_client:
            await client.aclose()
