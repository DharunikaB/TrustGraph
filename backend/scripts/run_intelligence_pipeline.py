"""CLI entrypoint: run the M2 intelligence pipeline against the database.

Usage:
    python scripts/run_intelligence_pipeline.py
    python scripts/run_intelligence_pipeline.py --output clusters.json
    python scripts/run_intelligence_pipeline.py --limit 5 --verbose

Prints a summary (cluster count size distribution, timing) and,
optionally, writes the full structured evidence list to a JSON file.
This is both the "example command to run M2" and the manual
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
from app.intelligence.pipeline import run_pipeline_async  # noqa: E402


def _json_default(value):
    # Signal dicts can contain numpy scalar types and pandas Timestamps
    # depending on the source data -- make json.dumps robust to both.
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


async def main_async(args: argparse.Namespace) -> None:
    start = time.perf_counter()
    async with AsyncSessionLocal() as session:
        results = await run_pipeline_async(session)
    elapsed = time.perf_counter() - start

    sizes = sorted(len(c["customers"]) for c in results)
    print(f"Candidate clusters found: {len(results)}")
    if sizes:
        print(f"Cluster sizes: min={sizes[0]} max={sizes[-1]} median={sizes[len(sizes) // 2]}")
    print(f"Pipeline runtime: {elapsed:.2f}s")

    if args.verbose:
        for cluster in results[: args.limit]:
            print(f"\n--- {cluster['cluster_id']} ({len(cluster['customers'])} customers) ---")
            for line in cluster["evidence"]:
                print(f"  - {line}")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(results, indent=2, default=_json_default))
        print(f"\nWrote {len(results)} cluster(s) to {out_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the M2 intelligence pipeline")
    parser.add_argument("--output", type=str, default=None, help="Write full JSON output here")
    parser.add_argument(
        "--verbose", action="store_true", help="Print evidence for each cluster to stdout"
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="Max clusters to print with --verbose"
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
