"""M3 risk pipeline -- the DETECTION path.

    M2 candidate clusters (with structured evidence)
        |
        v
    RISK SCORING        scoring.py
        |
        v
    FINANCIAL EXPOSURE   exposure.py
        |
        v
    ScoredCluster list

This module never imports `GroundTruth` and never touches the
`ground_truth` table -- ground truth is evaluation-only and lives in
`evaluation.py`, which is a strictly separate path (see that module's
docstring). Mixing the two here would defeat the entire point of
keeping detection and evaluation apart.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.config import IntelligenceConfig
from app.intelligence.data_loader import RawData, load_raw_data
from app.intelligence.pipeline import run_pipeline
from app.risk.config import RiskConfig
from app.risk.exposure import compute_exposure
from app.risk.models import ScoredCluster
from app.risk.scoring import compute_risk_assessment


def score_clusters(
    m2_results: list[dict], data: RawData, config: RiskConfig | None = None
) -> list[ScoredCluster]:
    """Score a list of M2 candidate-cluster evidence dicts.

    Synchronous and side-effect free, like M2's `run_pipeline` -- takes
    M2 output + the same `RawData` M2 was built from, returns
    `ScoredCluster` objects. This is what tests call directly.
    """
    config = config or RiskConfig()

    scored = []
    for cluster in m2_results:
        risk = compute_risk_assessment(cluster["signals"], config)
        exposure = compute_exposure(cluster["transactions"], data)
        scored.append(
            ScoredCluster(
                cluster_id=cluster["cluster_id"],
                customers=cluster["customers"],
                devices=cluster["devices"],
                networks=cluster["networks"],
                transactions=cluster["transactions"],
                risk=risk,
                exposure=exposure,
                signals=cluster["signals"],
                evidence=cluster["evidence"],
            )
        )
    return scored


async def run_risk_pipeline_async(
    session: AsyncSession,
    intelligence_config: IntelligenceConfig | None = None,
    risk_config: RiskConfig | None = None,
) -> list[ScoredCluster]:
    """Load data, run M2, then M3 scoring -- a single DB round trip.

    Used by the FastAPI debug endpoints and
    `scripts/run_risk_pipeline.py`.
    """
    data = await load_raw_data(session)
    m2_results = run_pipeline(data, intelligence_config)
    return score_clusters(m2_results, data, risk_config)
