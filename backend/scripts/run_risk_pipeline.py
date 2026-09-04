"""CLI entrypoint: run the M3 risk engine (and optionally evaluation).

Usage:
    python scripts/run_risk_pipeline.py
    python scripts/run_risk_pipeline.py --verbose --limit 5
    python scripts/run_risk_pipeline.py --evaluate
    python scripts/run_risk_pipeline.py --output scored_clusters.json --evaluate --evaluation-output evaluation.json

This is both the "example command to run M3" and the manual
verification tool used before declaring the milestone complete.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.risk.pipeline import run_risk_pipeline_async  # noqa: E402
from app.risk.evaluation import evaluate, load_ground_truth  # noqa: E402


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


async def main_async(args: argparse.Namespace) -> None:
    scoring_start = time.perf_counter()
    async with AsyncSessionLocal() as session:
        scored = await run_risk_pipeline_async(session)
    scoring_elapsed = time.perf_counter() - scoring_start

    scored_sorted = sorted(scored, key=lambda c: c.risk.score, reverse=True)
    scores = [c.risk.score for c in scored_sorted]

    print(f"Scored clusters: {len(scored_sorted)}")
    if scores:
        print(f"Score range: min={min(scores):.1f} max={max(scores):.1f} "
              f"median={sorted(scores)[len(scores) // 2]:.1f}")
    from collections import Counter
    level_counts = Counter(c.risk.level.value for c in scored_sorted)
    print(f"Risk levels: {dict(level_counts)}")
    print(f"Scoring runtime: {scoring_elapsed:.2f}s")

    if args.verbose:
        for cluster in scored_sorted[: args.limit]:
            print(f"\n--- {cluster.cluster_id} | score={cluster.risk.score} | {cluster.risk.level.value} ---")
            print(f"  exposure: {cluster.exposure.transaction_count} tx, "
                  f"Rs {cluster.exposure.transaction_value:,.2f} transaction value, "
                  f"Rs {cluster.exposure.returned_value:,.2f} returned")
            for contributor in cluster.risk.contributors:
                print(f"  [{contributor.contribution:5.2f}/{contributor.max_contribution:.0f}] "
                      f"{contributor.signal}: {contributor.evidence}")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(
            json.dumps([c.model_dump() for c in scored_sorted], indent=2, default=_json_default)
        )
        print(f"\nWrote {len(scored_sorted)} scored cluster(s) to {out_path}")

    if args.evaluate:
        eval_start = time.perf_counter()
        async with AsyncSessionLocal() as session:
            ground_truth = await load_ground_truth(session)
        report = evaluate(scored, ground_truth)
        eval_elapsed = time.perf_counter() - eval_start

        print(f"\n=== Evaluation (threshold={report['evaluation_threshold']}) ===")
        print(f"Evaluation runtime: {eval_elapsed:.2f}s")
        print(f"Cluster-level:  {report['cluster_level']}")
        print(f"Customer-level: {report['customer_level']}")
        print(f"Summary: {report['summary']}")

        if args.evaluation_output:
            eval_path = Path(args.evaluation_output)
            eval_path.write_text(json.dumps(report, indent=2, default=_json_default))
            print(f"\nWrote evaluation report to {eval_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the M3 risk engine")
    parser.add_argument("--output", type=str, default=None, help="Write scored clusters JSON here")
    parser.add_argument("--verbose", action="store_true", help="Print per-cluster breakdown")
    parser.add_argument("--limit", type=int, default=10, help="Max clusters to print with --verbose")
    parser.add_argument("--evaluate", action="store_true", help="Also run evaluation against ground truth")
    parser.add_argument("--evaluation-output", type=str, default=None, help="Write evaluation JSON here")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
