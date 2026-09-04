"""Verify the trained ML runtime against the canonical seed-42 pipeline."""

from __future__ import annotations

import asyncio

from app.db.session import AsyncSessionLocal
from app.ml.service import MLService
from app.risk.pipeline import run_risk_pipeline_async


async def main() -> None:
    service = MLService()
    if not service.enabled:
        raise RuntimeError("Train the ML artifact first.")

    async with AsyncSessionLocal() as session:
        clusters = list(await run_risk_pipeline_async(session=session))

    ranked = service.prioritize(clusters)
    print("TRUSTGRAPH ML RUNTIME VERIFICATION")
    print(f"Candidates: {len(ranked)}")
    print("Top 10:")
    for cluster, assessment in ranked[:10]:
        print(
            f"  #{assessment.priority_rank:02d} {cluster.cluster_id} "
            f"risk={cluster.risk.score:.2f} "
            f"ml={assessment.probability:.4f} "
            f"ml_pred={assessment.prediction} "
            f"disagreement={assessment.disagreement}"
        )

    disagreements = sum(1 for _, a in ranked if a.disagreement)
    print(f"Detector/ML disagreements: {disagreements}/{len(ranked)}")
    print("Runtime uses no ground truth and does not modify deterministic risk scores.")


if __name__ == "__main__":
    asyncio.run(main())
