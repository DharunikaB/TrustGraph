"""CLI entrypoint: run M4 investigations against the database.

Usage:
    python scripts/run_investigation.py                       # investigate top-scored cluster (mock)
    python scripts/run_investigation.py --cluster-id cc-0002   # investigate a specific cluster
    python scripts/run_investigation.py --limit 5              # investigate the top 5 by risk score
    python scripts/run_investigation.py --live                 # force the REAL Gemini client (requires GEMINI_API_KEY)

Without --live, always uses the mock client regardless of whether
GEMINI_API_KEY is set -- this script's default purpose is
demonstrating the pipeline offline. Use --live for the one-off,
manual, real-Gemini verification described in the M4 README.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.agent.context import build_investigation_context  # noqa: E402
from app.agent.gemini_client import MockGeminiClient, RealGeminiClient  # noqa: E402
from app.agent.investigator import investigate  # noqa: E402
from app.risk.pipeline import run_risk_pipeline_async  # noqa: E402


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):  # enums
        return value.value
    if hasattr(value, "item"):
        return value.item()
    return str(value)


async def main_async(args: argparse.Namespace) -> None:
    settings = get_settings()

    if args.live:
        if not settings.GEMINI_API_KEY:
            print("ERROR: --live requires GEMINI_API_KEY to be set. Aborting.")
            return
        client = RealGeminiClient(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
            max_retries=settings.GEMINI_MAX_RETRIES,
        )
        print(f"Using REAL Gemini client (model={settings.GEMINI_MODEL})")
    else:
        client = MockGeminiClient()
        print("Using MOCK Gemini client (pass --live for a real API call)")

    async with AsyncSessionLocal() as session:
        scored = await run_risk_pipeline_async(session)

    scored_sorted = sorted(scored, key=lambda c: c.risk.score, reverse=True)

    if args.cluster_id:
        targets = [c for c in scored_sorted if c.cluster_id == args.cluster_id]
        if not targets:
            print(f"No candidate cluster with id {args.cluster_id!r} in the current run.")
            return
    else:
        targets = scored_sorted[: args.limit]

    results = []
    for cluster in targets:
        request = build_investigation_context(cluster)
        result = await investigate(request, client)
        results.append(result)

        print(f"\n=== {result.cluster_id} | status={result.status.value} | "
              f"model={result.metadata.model} | latency={result.metadata.latency_ms:.1f}ms ===")
        if result.status.value == "COMPLETED":
            print(f"  classification: {result.assessment.classification.value}")
            print(f"  severity: {result.assessment.severity.value}  confidence: {result.assessment.confidence}")
            print(f"  recommended_action: {result.recommended_action.value}")
            print(f"  summary: {result.summary}")
            for finding in result.key_findings:
                print(f"  - {finding.finding} (refs: {finding.evidence_refs})")
        else:
            print(f"  error: {result.metadata.error}")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(
            json.dumps([r.model_dump(mode="json") for r in results], indent=2, default=_json_default)
        )
        print(f"\nWrote {len(results)} investigation result(s) to {out_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run M4 AI investigations")
    parser.add_argument("--cluster-id", type=str, default=None)
    parser.add_argument("--limit", type=int, default=1, help="How many top-scored clusters to investigate")
    parser.add_argument("--live", action="store_true", help="Use the REAL Gemini client (requires GEMINI_API_KEY)")
    parser.add_argument("--output", type=str, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
