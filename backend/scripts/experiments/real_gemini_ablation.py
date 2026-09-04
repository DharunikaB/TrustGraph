"""
TrustGraph REAL Gemini Policy Ablation.

LAB ONLY.

Compares the deterministic Policy Engine baseline against the same
Policy Engine when supplied with a real Gemini investigation.

The experiment intentionally does NOT use ground truth for:
- sample selection
- investigation
- policy decisions

Real Gemini failures are recorded separately and are never silently
replaced with Mock Gemini.
"""

from __future__ import annotations

import asyncio
import csv
import random
import time
from collections import Counter
from pathlib import Path

from app.agent.models import (
    InvestigationMetadata,
    InvestigationResult,
    InvestigationStatus,
)
from app.agent.pipeline import investigate_scored_cluster
from app.db.session import AsyncSessionLocal
from app.policy.engine import PolicyEngine
from app.risk.pipeline import run_risk_pipeline_async


RANDOM_SEED = 20260903
SAMPLE_SIZE = 30

OUTPUT_DIR = Path("artifacts/gemini_experiments")
OUTPUT_CSV = OUTPUT_DIR / "real_gemini_policy_ablation.csv"
OUTPUT_REPORT = OUTPUT_DIR / "REAL_GEMINI_ABLATION.md"


def select_stratified_sample(clusters):
    """
    Select a risk-stratified sample using only M3 risk level.

    Target:
        ~10 HIGH/CRITICAL
        ~10 MEDIUM
        ~10 LOW

    Ground truth is never consulted.
    """
    rng = random.Random(RANDOM_SEED)

    groups = {
        "HIGH_CRITICAL": [
            c
            for c in clusters
            if c.risk.level.value in {"HIGH", "CRITICAL"}
        ],
        "MEDIUM": [
            c
            for c in clusters
            if c.risk.level.value == "MEDIUM"
        ],
        "LOW": [
            c
            for c in clusters
            if c.risk.level.value == "LOW"
        ],
    }

    selected = []

    targets = {
        "HIGH_CRITICAL": 10,
        "MEDIUM": 10,
        "LOW": 10,
    }

    for name, target in targets.items():
        candidates = list(groups[name])
        rng.shuffle(candidates)
        selected.extend(candidates[:target])

    selected_ids = {c.cluster_id for c in selected}

    remaining = [
        c
        for c in clusters
        if c.cluster_id not in selected_ids
    ]

    rng.shuffle(remaining)

    if len(selected) < SAMPLE_SIZE:
        selected.extend(
            remaining[: SAMPLE_SIZE - len(selected)]
        )

    return sorted(
        selected[:SAMPLE_SIZE],
        key=lambda c: c.cluster_id,
    )


def build_no_ai_investigation(cluster) -> InvestigationResult:
    """
    Explicit no-Gemini baseline.

    Policy Engine treats AI_UNAVAILABLE as:
        deterministic risk + exposure baseline.
    """
    return InvestigationResult(
        cluster_id=cluster.cluster_id,
        status=InvestigationStatus.AI_UNAVAILABLE,
        metadata=InvestigationMetadata(
            model="NO_GEMINI_BASELINE",
            latency_ms=0.0,
            error="Gemini intentionally omitted for ablation baseline",
        ),
    )


def safe(value):
    """Convert enums/None to CSV-friendly values."""
    if value is None:
        return ""

    if hasattr(value, "value"):
        return value.value

    return str(value)


async def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 72)
    print("TRUSTGRAPH — REAL GEMINI POLICY ABLATION")
    print("=" * 72)
    print()
    print(f"Random seed : {RANDOM_SEED}")
    print(f"Sample size : {SAMPLE_SIZE}")
    print()

    # --------------------------------------------------------------
    # Run M2 + M3 exactly once.
    # --------------------------------------------------------------
    async with AsyncSessionLocal() as session:
        print("Running M2 + M3 risk pipeline...")

        started = time.perf_counter()

        clusters = await run_risk_pipeline_async(session)

        pipeline_ms = (
            time.perf_counter() - started
        ) * 1000

    print(f"Candidate clusters: {len(clusters)}")
    print(f"Pipeline time      : {pipeline_ms:.1f} ms")
    print()

    sample = select_stratified_sample(clusters)

    if not sample:
        raise RuntimeError(
            "No candidate clusters available for ablation."
        )

    print("Selected sample:")
    print(
        Counter(
            c.risk.level.value
            for c in sample
        )
    )
    print()

    policy_engine = PolicyEngine()

    rows = []

    # --------------------------------------------------------------
    # Run real Gemini sequentially.
    # --------------------------------------------------------------
    for index, cluster in enumerate(
        sample,
        start=1,
    ):
        print(
            f"[{index:02d}/{len(sample):02d}] "
            f"{cluster.cluster_id} "
            f"{cluster.risk.level.value} "
            f"{cluster.risk.score:.2f}"
        )

        # ----------------------------------------------------------
        # BASELINE — Gemini intentionally unavailable
        # ----------------------------------------------------------
        baseline_investigation = (
            build_no_ai_investigation(cluster)
        )

        baseline_decision = policy_engine.evaluate(
            cluster,
            baseline_investigation,
        )

        # ----------------------------------------------------------
        # REAL GEMINI
        # ----------------------------------------------------------
        gemini_started = time.perf_counter()

        try:
            investigation = await investigate_scored_cluster(
                cluster
            )

            gemini_wall_ms = (
                time.perf_counter() - gemini_started
            ) * 1000

            gemini_status = investigation.status.value
            gemini_error = investigation.metadata.error

            if (
                investigation.status
                == InvestigationStatus.COMPLETED
            ):
                gemini_decision = policy_engine.evaluate(
                    cluster,
                    investigation,
                )

                decision_changed = (
                    gemini_decision.decision.value
                    != baseline_decision.decision.value
                )

                recommendation = safe(
                    investigation.recommended_action
                )

                classification = (
                    safe(
                        investigation.assessment.classification
                    )
                    if investigation.assessment
                    else ""
                )

                confidence = (
                    investigation.assessment.confidence
                    if investigation.assessment
                    else ""
                )

                severity = (
                    safe(
                        investigation.assessment.severity
                    )
                    if investigation.assessment
                    else ""
                )

                ai_followed = (
                    gemini_decision.ai_recommendation_followed
                )

                print(
                    f"    Gemini : "
                    f"{classification} "
                    f"confidence={confidence}"
                )

                print(
                    f"    AI     : "
                    f"{recommendation}"
                )

                print(
                    f"    Policy : "
                    f"{baseline_decision.decision.value} "
                    f"-> "
                    f"{gemini_decision.decision.value}"
                    + (
                        " *** CHANGED ***"
                        if decision_changed
                        else ""
                    )
                )

            else:
                gemini_decision = None
                decision_changed = False
                recommendation = ""
                classification = ""
                confidence = ""
                severity = ""
                ai_followed = False

                print(
                    f"    Gemini : "
                    f"{gemini_status}"
                )

        except Exception as exc:
            gemini_wall_ms = (
                time.perf_counter() - gemini_started
            ) * 1000

            gemini_status = "EXCEPTION"
            gemini_error = str(exc)

            gemini_decision = None
            decision_changed = False
            recommendation = ""
            classification = ""
            confidence = ""
            severity = ""
            ai_followed = False

            print(
                f"    Gemini : "
                f"EXCEPTION — {exc}"
            )

        # ----------------------------------------------------------
        # Save one experiment row.
        # ----------------------------------------------------------
        rows.append(
            {
                "cluster_id": cluster.cluster_id,
                "risk_score": cluster.risk.score,
                "risk_level": safe(cluster.risk.level),
                "exposure_inr": cluster.exposure.estimated_exposure,
                "baseline_policy_decision": safe(
                    baseline_decision.decision
                ),
                "baseline_reason_codes": "|".join(
                    safe(reason)
                    for reason in baseline_decision.reason_codes
                ),
                "gemini_status": gemini_status,
                "gemini_classification": classification,
                "gemini_severity": severity,
                "gemini_confidence": confidence,
                "gemini_recommendation": recommendation,
                "gemini_policy_decision": (
                    safe(gemini_decision.decision)
                    if gemini_decision
                    else ""
                ),
                "ai_recommendation_followed": ai_followed,
                "decision_changed": decision_changed,
                "gemini_latency_ms": round(
                    gemini_wall_ms,
                    2,
                ),
                "gemini_error": gemini_error or "",
            }
        )

        print()

    # --------------------------------------------------------------
    # Write CSV.
    # --------------------------------------------------------------
    fieldnames = list(rows[0].keys())

    with OUTPUT_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    # --------------------------------------------------------------
    # Aggregate results.
    # --------------------------------------------------------------
    completed = [
        row
        for row in rows
        if row["gemini_status"] == "COMPLETED"
    ]

    failed = [
        row
        for row in rows
        if row["gemini_status"] != "COMPLETED"
    ]

    changed = [
        row
        for row in completed
        if row["decision_changed"]
    ]

    followed = [
        row
        for row in completed
        if row["ai_recommendation_followed"]
    ]

    overridden = [
        row
        for row in completed
        if not row["ai_recommendation_followed"]
    ]

    total_completed = len(completed)

    change_rate = (
        len(changed) / total_completed
        if total_completed
        else 0.0
    )

    follow_rate = (
        len(followed) / total_completed
        if total_completed
        else 0.0
    )

    override_rate = (
        len(overridden) / total_completed
        if total_completed
        else 0.0
    )

    latencies = [
        float(row["gemini_latency_ms"])
        for row in completed
    ]

    mean_latency = (
        sum(latencies) / len(latencies)
        if latencies
        else 0.0
    )

    classifications = Counter(
        row["gemini_classification"]
        for row in completed
    )

    baseline_decisions = Counter(
        row["baseline_policy_decision"]
        for row in rows
    )

    gemini_decisions = Counter(
        row["gemini_policy_decision"]
        for row in completed
    )

    # --------------------------------------------------------------
    # Write Markdown report.
    # --------------------------------------------------------------
    report_lines = [
        "# TrustGraph — Real Gemini Policy Ablation",
        "",
        "## Purpose",
        "",
        "This experiment measures whether a real Gemini investigation "
        "materially influences the downstream deterministic Policy "
        "Engine.",
        "",
        "The same M2+M3 `ScoredCluster` is evaluated twice:",
        "",
        "1. **Baseline:** Gemini intentionally unavailable.",
        "2. **AI path:** Real Gemini investigation supplied to the same "
        "Policy Engine.",
        "",
        "The Policy Engine remains the final decision authority.",
        "",
        "## Experiment Controls",
        "",
        "- Environment: LAB only",
        "- Gemini model: `gemini-3.5-flash`",
        f"- Random seed: `{RANDOM_SEED}`",
        f"- Sample size: `{len(rows)}`",
        "- M2+M3 pipeline executions: 1",
        "- Ground truth used for sampling: **No**",
        "- Ground truth used by investigation: **No**",
        "- Ground truth used by policy: **No**",
        "",
        "## Results",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Sampled clusters | {len(rows)} |",
        f"| Completed Gemini investigations | {total_completed} |",
        f"| Gemini failures | {len(failed)} |",
        f"| AI recommendation followed | "
        f"{len(followed)} / {total_completed} "
        f"({follow_rate:.1%}) |",
        f"| AI recommendation overridden | "
        f"{len(overridden)} / {total_completed} "
        f"({override_rate:.1%}) |",
        f"| Policy decisions changed | "
        f"{len(changed)} / {total_completed} "
        f"({change_rate:.1%}) |",
        f"| Mean Gemini latency | "
        f"{mean_latency:.1f} ms |",
        "",
        "## Gemini Classifications",
        "",
        "```text",
        str(dict(classifications)),
        "```",
        "",
        "## Baseline Policy Decisions",
        "",
        "```text",
        str(dict(baseline_decisions)),
        "```",
        "",
        "## Gemini-Aware Policy Decisions",
        "",
        "```text",
        str(dict(gemini_decisions)),
        "```",
        "",
        "## Interpretation",
        "",
        "This experiment should be interpreted as an ablation of "
        "downstream policy influence, not as a fraud-detection "
        "accuracy benchmark.",
        "",
        "A non-zero decision-change rate demonstrates that the "
        "structured Gemini investigation can materially influence "
        "Policy Engine outcomes.",
        "",
        "A non-zero override rate demonstrates that deterministic "
        "policy controls can reject or constrain an AI recommendation.",
        "",
        "AI remains advisory and bounded; it does not directly "
        "execute actions or override deterministic safety controls.",
        "",
        "## Limitations",
        "",
        "- The sample is intentionally small because this is a real "
        "provider experiment rather than an offline simulation.",
        "- Provider availability and latency can vary.",
        "- Synthetic TrustGraph data is not representative of "
        "production payment traffic.",
        "- This experiment does not establish production "
        "fraud-detection performance.",
        "- Gemini failures are recorded separately and are not "
        "silently converted into successful AI investigations.",
        "",
        "## Artifact",
        "",
        "Raw experiment data:",
        "",
        f"`{OUTPUT_CSV.as_posix()}`",
        "",
    ]

    OUTPUT_REPORT.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    # --------------------------------------------------------------
    # Final console summary.
    # --------------------------------------------------------------
    print("=" * 72)
    print("REAL GEMINI ABLATION COMPLETE")
    print("=" * 72)
    print()
    print(
        f"Sampled clusters       : {len(rows)}"
    )
    print(
        f"Gemini completed       : {total_completed}"
    )
    print(
        f"Gemini failures        : {len(failed)}"
    )
    print()
    print(
        f"AI recommendation followed : "
        f"{len(followed)}/{total_completed} "
        f"({follow_rate:.1%})"
    )
    print(
        f"AI recommendation overridden: "
        f"{len(overridden)}/{total_completed} "
        f"({override_rate:.1%})"
    )
    print(
        f"Policy decisions changed    : "
        f"{len(changed)}/{total_completed} "
        f"({change_rate:.1%})"
    )
    print()
    print(
        f"Mean Gemini latency     : "
        f"{mean_latency:.1f} ms"
    )
    print()
    print(
        f"CSV    : {OUTPUT_CSV}"
    )
    print(
        f"Report : {OUTPUT_REPORT}"
    )
    print()


if __name__ == "__main__":
    asyncio.run(main())