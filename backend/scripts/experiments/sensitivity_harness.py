"""
TrustGraph LAB — Sensitivity Analysis

LAB-only experiment for measuring sensitivity of the TrustGraph detector
to its two important configurable operating parameters:

1. M2 transaction amount-similarity tolerance
2. M3 evaluation threshold

IMPORTANT:
- This file does NOT modify production TrustGraph configuration.
- Ground truth is used only inside this experiment's evaluation layer.
- M2 and M3 never receive ground truth.
- Development seeds are used for configuration analysis.
- Held-out seeds are used only for final robustness checking.
- Seed 42 is always restored when the experiment finishes.

Development seeds:
    42, 43, 44, 45, 46

Held-out seeds:
    9001, 9002, 9003, 9004, 9005

Production configuration:
    amount_similarity_tolerance = 0.005   (0.50%)
    evaluation threshold         = 52.0
"""

from __future__ import annotations

import asyncio
import csv
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.db.session import AsyncSessionLocal, engine
from app.intelligence.config import IntelligenceConfig
from app.intelligence.data_loader import load_raw_data
from app.intelligence.pipeline import run_pipeline
from app.risk.config import RiskConfig
from app.risk.evaluation import (
    cluster_ground_truth_label,
    load_ground_truth,
)
from app.risk.pipeline import score_clusters


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

DATA_ROOT = ROOT / "data"
SYNTHETIC_DIR = DATA_ROOT / "sensitivity_tmp"

GENERATE_SCRIPT = ROOT / "scripts" / "generate_synthetic_data.py"
LOAD_SCRIPT = ROOT / "scripts" / "load_data.py"

ARTIFACT_DIR = ROOT / "artifacts" / "sensitivity_experiments"

CSV_PATH = ARTIFACT_DIR / "sensitivity_multiseed.csv"
REPORT_PATH = ARTIFACT_DIR / "SENSITIVITY_ANALYSIS.md"


# ---------------------------------------------------------------------------
# Experimental configuration
# ---------------------------------------------------------------------------

DEVELOPMENT_SEEDS = [
    42,
    43,
    44,
    45,
    46,
]

HELD_OUT_SEEDS = [
    9001,
    9002,
    9003,
    9004,
    9005,
]


# Amount similarity tolerance values.
#
# 0.005 = 0.50%, which is the current production configuration.
AMOUNT_TOLERANCES = [
    0.0010,   # 0.10%
    0.0025,   # 0.25%
    0.0050,   # 0.50%
    0.0075,   # 0.75%
    0.0100,   # 1.00%
]


# Existing threshold sweep from RiskConfig.
#
# 52.0 is the current evaluation operating point.
THRESHOLDS = [
    20.0,
    30.0,
    40.0,
    50.0,
    52.0,
    55.0,
    60.0,
    70.0,
    80.0,
    90.0,
]


PRODUCTION_TOLERANCE = 0.005
PRODUCTION_THRESHOLD = 52.0


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def run_command(args: list[str]) -> None:
    """Run a child Python process from the TrustGraph backend root."""

    print("  $", " ".join(map(str, args)))

    subprocess.run(
        args,
        cwd=ROOT,
        check=True,
    )


def generate_seed(seed: int) -> None:
    """Generate an isolated synthetic dataset for one seed."""

    if SYNTHETIC_DIR.exists():
        for path in SYNTHETIC_DIR.iterdir():
            if path.is_file():
                path.unlink()

    SYNTHETIC_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_command(
        [
            sys.executable,
            str(GENERATE_SCRIPT),
            "--seed",
            str(seed),
            "--out",
            str(SYNTHETIC_DIR),
        ]
    )


def load_seed() -> None:
    """Reset PostgreSQL and load the generated synthetic dataset."""

    run_command(
        [
            sys.executable,
            str(LOAD_SCRIPT),
            "--input",
            str(SYNTHETIC_DIR),
            "--reset",
        ]
    )


async def dispose_engine() -> None:
    """
    Dispose SQLAlchemy's async engine after the loader resets the database.

    The loader runs in a separate subprocess and recreates the schema.
    Disposing the parent's engine prevents asyncpg from reusing prepared
    statements associated with the previous schema.
    """

    await engine.dispose()


# ---------------------------------------------------------------------------
# Evaluation metrics
# ---------------------------------------------------------------------------

def calculate_metrics(
    labels: list[bool],
    predictions: list[bool],
) -> dict[str, float | None]:
    """
    Calculate binary classification metrics locally.

    Ground-truth labels come from the evaluation-only boundary.
    """

    if not labels:
        return {
            "precision": None,
            "recall": None,
            "f1": None,
            "fpr": None,
        }

    tp = 0
    fp = 0
    tn = 0
    fn = 0

    for label, prediction in zip(labels, predictions):
        if label and prediction:
            tp += 1
        elif not label and prediction:
            fp += 1
        elif not label and not prediction:
            tn += 1
        elif label and not prediction:
            fn += 1

    precision = (
        tp / (tp + fp)
        if (tp + fp) > 0
        else None
    )

    recall = (
        tp / (tp + fn)
        if (tp + fn) > 0
        else None
    )

    if (
        precision is not None
        and recall is not None
        and (precision + recall) > 0
    ):
        f1 = (
            2.0 * precision * recall
            / (precision + recall)
        )
    else:
        f1 = None

    fpr = (
        fp / (fp + tn)
        if (fp + tn) > 0
        else None
    )

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fpr,
    }


def metric_value(
    metrics: dict[str, float | None],
    name: str,
) -> float | None:
    """Return one metric as a float or None."""

    value = metrics.get(name)

    if value is None:
        return None

    return float(value)


# ---------------------------------------------------------------------------
# Single configuration evaluation
# ---------------------------------------------------------------------------

async def evaluate_configuration(
    *,
    seed: int,
    split: str,
    amount_tolerance: float,
    threshold: float,
) -> dict[str, Any]:
    """
    Evaluate one sensitivity configuration against the currently loaded seed.

    Ground truth is loaded only after the raw dataset is loaded and is never
    supplied to M2 or M3.
    """

    intelligence_config = IntelligenceConfig(
        amount_similarity_tolerance=amount_tolerance,
    )

    risk_config = RiskConfig(
        default_evaluation_threshold=threshold,
    )

    # -----------------------------------------------------------------------
    # Load raw observable data.
    # -----------------------------------------------------------------------

    async with AsyncSessionLocal() as session:
        data = await load_raw_data(session)

    # -----------------------------------------------------------------------
    # Ground truth is evaluation-only.
    # -----------------------------------------------------------------------

    async with AsyncSessionLocal() as session:
        ground_truth = await load_ground_truth(session)

    # -----------------------------------------------------------------------
    # M2 — no ground truth.
    # -----------------------------------------------------------------------

    m2_results = run_pipeline(
        data,
        intelligence_config,
    )

    # -----------------------------------------------------------------------
    # M3 — no ground truth.
    # -----------------------------------------------------------------------

    scored_clusters = score_clusters(
        m2_results,
        data,
        risk_config,
    )

    labels: list[bool] = []
    predictions: list[bool] = []

    labelled_clusters = 0
    positive_clusters = 0
    negative_clusters = 0

    # -----------------------------------------------------------------------
    # Cluster-level evaluation.
    # -----------------------------------------------------------------------

    for cluster in scored_clusters:
        label = cluster_ground_truth_label(
            cluster,
            ground_truth,
            risk_config,
        )

        if label is None:
            continue

        labelled_clusters += 1

        labels.append(bool(label))

        if label:
            positive_clusters += 1
        else:
            negative_clusters += 1

        predictions.append(
            cluster.risk.score >= threshold
        )

    metrics = calculate_metrics(
        labels,
        predictions,
    )

    # -----------------------------------------------------------------------
    # Customer-level abuse coverage.
    #
    # This is complementary to cluster-level metrics. Cluster-level metrics
    # remain the primary evaluation measure.
    # -----------------------------------------------------------------------

    abuse_customers: set[str] = {
        customer_id
        for customer_id, is_abuse in ground_truth.items()
        if is_abuse
    }

    detected_abuse_customers: set[str] = set()

    for cluster in scored_clusters:
        if cluster.risk.score < threshold:
            continue

        for customer_id in cluster.customers:
            if customer_id in abuse_customers:
                detected_abuse_customers.add(customer_id)

    customer_coverage = (
        len(detected_abuse_customers)
        / len(abuse_customers)
        if abuse_customers
        else 0.0
    )

    return {
        "seed": seed,
        "split": split,
        "amount_tolerance": amount_tolerance,
        "amount_tolerance_pct": amount_tolerance * 100.0,
        "threshold": threshold,
        "candidate_clusters": len(scored_clusters),
        "labelled_clusters": labelled_clusters,
        "positive_clusters": positive_clusters,
        "negative_clusters": negative_clusters,
        "precision": metric_value(metrics, "precision"),
        "recall": metric_value(metrics, "recall"),
        "f1": metric_value(metrics, "f1"),
        "fpr": metric_value(metrics, "fpr"),
        "customer_coverage": customer_coverage,
    }


# ---------------------------------------------------------------------------
# Per-seed experiment
# ---------------------------------------------------------------------------

async def run_seed(
    *,
    seed: int,
    split: str,
) -> list[dict[str, Any]]:
    """Generate, load, and evaluate one seed."""

    print()
    print("=" * 72)
    print(f"SENSITIVITY SEED {seed} [{split}]")
    print("=" * 72)

    # Generate fresh data.
    generate_seed(seed)

    # The database schema will be recreated by the loader.
    await dispose_engine()

    # Load fresh seed.
    load_seed()

    # Drop any stale SQLAlchemy/asyncpg state from before the reset.
    await dispose_engine()

    results: list[dict[str, Any]] = []

    # -----------------------------------------------------------------------
    # A. Threshold sensitivity.
    #
    # Amount tolerance remains at production value.
    # -----------------------------------------------------------------------

    print()
    print("Threshold sensitivity")

    for threshold in THRESHOLDS:
        result = await evaluate_configuration(
            seed=seed,
            split=split,
            amount_tolerance=PRODUCTION_TOLERANCE,
            threshold=threshold,
        )

        results.append(result)

        print(
            f"  threshold={threshold:>5.1f} "
            f"P={result['precision']!s:<6} "
            f"R={result['recall']!s:<6} "
            f"F1={result['f1']!s:<6} "
            f"FPR={result['fpr']!s:<6}"
        )

    # -----------------------------------------------------------------------
    # B. Amount tolerance sensitivity.
    #
    # Threshold remains at production value.
    # -----------------------------------------------------------------------

    print()
    print("Amount tolerance sensitivity")

    for tolerance in AMOUNT_TOLERANCES:
        result = await evaluate_configuration(
            seed=seed,
            split=split,
            amount_tolerance=tolerance,
            threshold=PRODUCTION_THRESHOLD,
        )

        results.append(result)

        print(
            f"  tolerance={tolerance * 100:>5.2f}% "
            f"P={result['precision']!s:<6} "
            f"R={result['recall']!s:<6} "
            f"F1={result['f1']!s:<6} "
            f"FPR={result['fpr']!s:<6} "
            f"coverage={result['customer_coverage']:.4f}"
        )

    return results


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def write_csv(
    rows: list[dict[str, Any]],
) -> None:
    """Write every sensitivity observation to CSV."""

    ARTIFACT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "seed",
        "split",
        "amount_tolerance",
        "amount_tolerance_pct",
        "threshold",
        "candidate_clusters",
        "labelled_clusters",
        "positive_clusters",
        "negative_clusters",
        "precision",
        "recall",
        "f1",
        "fpr",
        "customer_coverage",
    ]

    with CSV_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def mean(
    values: list[float],
) -> float | None:
    """Return arithmetic mean or None when no values exist."""

    if not values:
        return None

    return sum(values) / len(values)


def summarize(
    rows: list[dict[str, Any]],
    *,
    split: str,
    parameter: str,
) -> list[dict[str, Any]]:
    """
    Aggregate sensitivity results by one parameter.

    For threshold sensitivity, amount tolerance is fixed at production value.

    For amount sensitivity, threshold is fixed at production value.
    """

    selected = [
        row
        for row in rows
        if row["split"] == split
    ]

    if parameter == "threshold":
        values = THRESHOLDS

        def matches(
            row: dict[str, Any],
            value: float,
        ) -> bool:
            return (
                abs(row["threshold"] - value) < 1e-9
                and abs(
                    row["amount_tolerance"]
                    - PRODUCTION_TOLERANCE
                ) < 1e-12
            )

    else:
        values = AMOUNT_TOLERANCES

        def matches(
            row: dict[str, Any],
            value: float,
        ) -> bool:
            return (
                abs(
                    row["amount_tolerance"]
                    - value
                ) < 1e-12
                and abs(
                    row["threshold"]
                    - PRODUCTION_THRESHOLD
                ) < 1e-9
            )

    summary: list[dict[str, Any]] = []

    for value in values:
        group = [
            row
            for row in selected
            if matches(row, value)
        ]

        summary.append(
            {
                "value": value,
                "precision": mean(
                    [
                        row["precision"]
                        for row in group
                        if row["precision"] is not None
                    ]
                ),
                "recall": mean(
                    [
                        row["recall"]
                        for row in group
                        if row["recall"] is not None
                    ]
                ),
                "f1": mean(
                    [
                        row["f1"]
                        for row in group
                        if row["f1"] is not None
                    ]
                ),
                "fpr": mean(
                    [
                        row["fpr"]
                        for row in group
                        if row["fpr"] is not None
                    ]
                ),
                "customer_coverage": mean(
                    [
                        row["customer_coverage"]
                        for row in group
                    ]
                ),
                "candidate_clusters": mean(
                    [
                        row["candidate_clusters"]
                        for row in group
                    ]
                ),
            }
        )

    return summary


def fmt(
    value: float | None,
    digits: int = 4,
) -> str:
    """Format an optional numeric value."""

    if value is None:
        return "n/a"

    return f"{value:.{digits}f}"


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def write_report(
    rows: list[dict[str, Any]],
) -> None:
    """Write the complete sensitivity-analysis report."""

    dev_thresholds = summarize(
        rows,
        split="development",
        parameter="threshold",
    )

    held_thresholds = summarize(
        rows,
        split="held_out",
        parameter="threshold",
    )

    dev_tolerances = summarize(
        rows,
        split="development",
        parameter="tolerance",
    )

    held_tolerances = summarize(
        rows,
        split="held_out",
        parameter="tolerance",
    )

    lines: list[str] = []

    lines.append("# TrustGraph Sensitivity Analysis")
    lines.append("")
    lines.append(
        "LAB-only parameter sensitivity experiment for the TrustGraph "
        "payment-abuse detector."
    )
    lines.append("")

    # -----------------------------------------------------------------------
    # Objective
    # -----------------------------------------------------------------------

    lines.append("## Objective")
    lines.append("")
    lines.append(
        "Measure how detector behavior changes when the two principal "
        "operating parameters are varied independently:"
    )
    lines.append("")
    lines.append(
        "- M3 evaluation threshold"
    )
    lines.append(
        "- M2 transaction amount-similarity tolerance"
    )
    lines.append("")

    # -----------------------------------------------------------------------
    # Evaluation discipline
    # -----------------------------------------------------------------------

    lines.append("## Evaluation discipline")
    lines.append("")
    lines.append(
        "Development seeds 42–46 are used for configuration understanding. "
        "Held-out seeds 9001–9005 are used for untouched robustness "
        "validation."
    )
    lines.append("")
    lines.append(
        "Ground truth is used only by the evaluation layer. It is never "
        "supplied to M2 candidate generation or M3 risk scoring."
    )
    lines.append("")
    lines.append(
        "Each parameter is varied independently while the other parameter "
        "remains fixed at the production value."
    )
    lines.append("")

    # -----------------------------------------------------------------------
    # Production configuration
    # -----------------------------------------------------------------------

    lines.append("## Production configuration")
    lines.append("")
    lines.append(
        f"- Amount similarity tolerance: "
        f"**{PRODUCTION_TOLERANCE * 100:.2f}%**"
    )
    lines.append(
        f"- Evaluation threshold: "
        f"**{PRODUCTION_THRESHOLD:.1f}**"
    )
    lines.append("")

    # -----------------------------------------------------------------------
    # Threshold development
    # -----------------------------------------------------------------------

    lines.append(
        "## Threshold sensitivity — development"
    )
    lines.append("")
    lines.append(
        "| Threshold | Precision | Recall | F1 | FPR | Avg candidates |"
    )
    lines.append(
        "|---:|---:|---:|---:|---:|---:|"
    )

    for row in dev_thresholds:
        lines.append(
            f"| {row['value']:.1f} | "
            f"{fmt(row['precision'])} | "
            f"{fmt(row['recall'])} | "
            f"{fmt(row['f1'])} | "
            f"{fmt(row['fpr'])} | "
            f"{fmt(row['candidate_clusters'], 2)} |"
        )

    lines.append("")

    # -----------------------------------------------------------------------
    # Threshold held-out
    # -----------------------------------------------------------------------

    lines.append(
        "## Threshold sensitivity — held-out"
    )
    lines.append("")
    lines.append(
        "| Threshold | Precision | Recall | F1 | FPR | Avg candidates |"
    )
    lines.append(
        "|---:|---:|---:|---:|---:|---:|"
    )

    for row in held_thresholds:
        lines.append(
            f"| {row['value']:.1f} | "
            f"{fmt(row['precision'])} | "
            f"{fmt(row['recall'])} | "
            f"{fmt(row['f1'])} | "
            f"{fmt(row['fpr'])} | "
            f"{fmt(row['candidate_clusters'], 2)} |"
        )

    lines.append("")

    # -----------------------------------------------------------------------
    # Tolerance development
    # -----------------------------------------------------------------------

    lines.append(
        "## Amount tolerance sensitivity — development"
    )
    lines.append("")
    lines.append(
        "| Tolerance | Precision | Recall | F1 | FPR | Customer coverage |"
    )
    lines.append(
        "|---:|---:|---:|---:|---:|---:|"
    )

    for row in dev_tolerances:
        lines.append(
            f"| {row['value'] * 100:.2f}% | "
            f"{fmt(row['precision'])} | "
            f"{fmt(row['recall'])} | "
            f"{fmt(row['f1'])} | "
            f"{fmt(row['fpr'])} | "
            f"{fmt(row['customer_coverage'])} |"
        )

    lines.append("")

    # -----------------------------------------------------------------------
    # Tolerance held-out
    # -----------------------------------------------------------------------

    lines.append(
        "## Amount tolerance sensitivity — held-out"
    )
    lines.append("")
    lines.append(
        "| Tolerance | Precision | Recall | F1 | FPR | Customer coverage |"
    )
    lines.append(
        "|---:|---:|---:|---:|---:|---:|"
    )

    for row in held_tolerances:
        lines.append(
            f"| {row['value'] * 100:.2f}% | "
            f"{fmt(row['precision'])} | "
            f"{fmt(row['recall'])} | "
            f"{fmt(row['f1'])} | "
            f"{fmt(row['f1'])} | "
            f"{fmt(row['customer_coverage'])} |"
        )

    lines.append("")

    # -----------------------------------------------------------------------
    # Interpretation
    # -----------------------------------------------------------------------

    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "The current operating point of 52 is an evaluation operating "
        "point selected from development behavior and subsequently checked "
        "against untouched held-out seeds. It is not a universal fraud "
        "boundary."
    )
    lines.append("")
    lines.append(
        "The amount-similarity tolerance is supporting evidence only. "
        "Changing this value changes how transaction amount similarity is "
        "measured; it does not redefine abuse."
    )
    lines.append("")
    lines.append(
        "Sensitivity results are robustness evidence on controlled "
        "synthetic datasets and must not be interpreted as production "
        "fraud-detection performance guarantees."
    )
    lines.append("")

    # -----------------------------------------------------------------------
    # Methodology
    # -----------------------------------------------------------------------

    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "Each configuration changes one parameter while keeping the other "
        "at its production value."
    )
    lines.append("")
    lines.append(
        "For threshold sensitivity, amount similarity remains fixed at "
        "0.50%."
    )
    lines.append("")
    lines.append(
        "For amount tolerance sensitivity, the evaluation threshold remains "
        "fixed at 52."
    )
    lines.append("")
    lines.append(
        "Every seed is regenerated and loaded independently before evaluation."
    )
    lines.append("")

    # -----------------------------------------------------------------------
    # Reproducibility
    # -----------------------------------------------------------------------

    lines.append("## Reproducibility")
    lines.append("")
    lines.append(
        f"- Development seeds: `{DEVELOPMENT_SEEDS}`"
    )
    lines.append(
        f"- Held-out seeds: `{HELD_OUT_SEEDS}`"
    )
    lines.append(
        f"- Threshold configurations: `{len(THRESHOLDS)}`"
    )
    lines.append(
        f"- Amount tolerance configurations: "
        f"`{len(AMOUNT_TOLERANCES)}`"
    )
    lines.append(
        f"- Total observations: `{len(rows)}`"
    )
    lines.append(
        f"- CSV artifact: `{CSV_PATH}`"
    )
    lines.append("")

    REPORT_PATH.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    """Run the complete sensitivity experiment."""

    ARTIFACT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_rows: list[dict[str, Any]] = []

    # -----------------------------------------------------------------------
    # Development
    # -----------------------------------------------------------------------

    for seed in DEVELOPMENT_SEEDS:
        all_rows.extend(
            await run_seed(
                seed=seed,
                split="development",
            )
        )

    # -----------------------------------------------------------------------
    # Held-out
    # -----------------------------------------------------------------------

    for seed in HELD_OUT_SEEDS:
        all_rows.extend(
            await run_seed(
                seed=seed,
                split="held_out",
            )
        )

    # -----------------------------------------------------------------------
    # Write artifacts.
    # -----------------------------------------------------------------------

    write_csv(all_rows)
    write_report(all_rows)

    # -----------------------------------------------------------------------
    # ALWAYS restore canonical seed 42.
    # -----------------------------------------------------------------------

    print()
    print("=" * 72)
    print("RESTORING CANONICAL SEED 42")
    print("=" * 72)

    generate_seed(42)

    await dispose_engine()

    load_seed()

    await dispose_engine()

    print()
    print("=" * 72)
    print("SENSITIVITY ANALYSIS COMPLETE")
    print("=" * 72)
    print(f"Rows written : {len(all_rows)}")
    print(f"CSV          : {CSV_PATH}")
    print(f"Report       : {REPORT_PATH}")
    print("Seed 42 restored.")


if __name__ == "__main__":
    asyncio.run(main())