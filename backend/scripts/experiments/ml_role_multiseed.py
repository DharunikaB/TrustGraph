"""
TrustGraph — ML Role Multiseed Experiment

LAB-ONLY.

Purpose:
    Evaluate the operational usefulness of the Gradient Boosting model
    across unseen synthetic seeds.

Roles evaluated:
    B. Candidate Prioritization
    C. Secondary Validation

Evaluation design:
    Development seeds:
        42, 43, 44, 45, 46

    Held-out seeds:
        9001, 9002, 9003, 9004, 9005

    The model is trained ONLY on development seeds and evaluated ONLY
    on held-out seeds.

Important:
    - Production TrustGraph code is not modified.
    - GroundTruth is used only through app.risk.evaluation.
    - GroundTruth is never part of the feature vector.
    - Deterministic risk score is never part of the ML feature vector.
    - Gemini output and policy decisions are never features.
    - The original seed-42 dataset is restored after the experiment.
    - SQLAlchemy's connection pool is disposed after every database reset
      to prevent stale asyncpg prepared-statement caches.

This is experimental analysis, not a production scoring change.
"""

from __future__ import annotations

import asyncio
import csv
import math
import shutil
import subprocess
import sys
from pathlib import Path

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline

from app.db.session import AsyncSessionLocal, engine
from app.risk.config import RiskConfig
from app.risk.evaluation import (
    cluster_ground_truth_label,
    load_ground_truth,
)
from app.risk.pipeline import run_risk_pipeline_async


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

DEVELOPMENT_SEEDS = [42, 43, 44, 45, 46]
HELD_OUT_SEEDS = [9001, 9002, 9003, 9004, 9005]

ALL_SEEDS = DEVELOPMENT_SEEDS + HELD_OUT_SEEDS

ML_THRESHOLD = 0.37
DETERMINISTIC_THRESHOLD = 52.0

TOP_K_FRACTION = 0.25

RANDOM_SEED = 20260903

BASE_DIR = Path(__file__).resolve().parents[2]

DATA_ROOT = (
    BASE_DIR
    / "data"
    / "ml_role_multiseed"
)

ORIGINAL_DATA_DIR = (
    BASE_DIR
    / "data"
    / "synthetic"
)

OUTPUT_DIR = (
    BASE_DIR
    / "artifacts"
    / "ml_role_experiments"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

CSV_PATH = (
    OUTPUT_DIR
    / "ml_role_multiseed.csv"
)

REPORT_PATH = (
    OUTPUT_DIR
    / "ML_ROLE_MULTISEED.md"
)


# ----------------------------------------------------------------------
# Observable feature vector
# ----------------------------------------------------------------------

FEATURE_NAMES = [
    "cluster_size",
    "num_devices",
    "max_customers_per_device",
    "shared_device_ratio",
    "num_networks",
    "max_customers_per_network",
    "shared_network_ratio",
    "creation_time_span_hours",
    "max_accounts_in_window",
    "burst_ratio",
    "num_transactions",
    "transactions_per_customer",
    "max_transactions_in_window",
    "activity_span_hours",
    "velocity_ratio_vs_baseline",
    "temporal_coordination_ratio",
    "amount_coefficient_of_variation",
    "distinct_amounts_shared_across_customers",
    "num_orders",
    "num_returns",
    "return_rate",
    "return_deviation_ratio",
    "top_customer_return_share",
    "num_customer_nodes",
    "num_device_nodes",
    "num_network_nodes",
    "num_edges",
    "density",
    "avg_customer_degree",
    "diameter",
]


# ----------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------

def safe_float(value: object) -> float:
    """Convert optional signal values into finite floats."""

    if value is None:
        return float("nan")

    try:
        value = float(value)
    except (TypeError, ValueError):
        return float("nan")

    if not math.isfinite(value):
        return float("nan")

    return value


def run_command(command: list[str]) -> None:
    """Run a subprocess and fail loudly if it exits unsuccessfully."""

    print()
    print("$ " + " ".join(command))
    print()

    subprocess.run(
        command,
        cwd=BASE_DIR,
        check=True,
    )


# ----------------------------------------------------------------------
# Synthetic dataset generation/loading
# ----------------------------------------------------------------------

def generate_seed(
    seed: int,
    output_dir: Path,
) -> None:
    """Generate one isolated synthetic dataset."""

    if output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_command(
        [
            sys.executable,
            "scripts/generate_synthetic_data.py",
            "--seed",
            str(seed),
            "--out",
            str(output_dir),
        ]
    )


async def load_seed(
    output_dir: Path,
) -> None:
    """
    Reset the LAB database, load one dataset, and dispose the
    SQLAlchemy connection pool.

    The loader drops/recreates the schema. Existing asyncpg pooled
    connections may retain prepared statements tied to the old schema.
    Disposing the engine forces subsequent operations to use fresh
    connections.
    """

    run_command(
        [
            sys.executable,
            "scripts/load_data.py",
            "--input",
            str(output_dir),
            "--reset",
        ]
    )

    await engine.dispose()


# ----------------------------------------------------------------------
# Feature extraction
# ----------------------------------------------------------------------

def cluster_to_features(
    cluster,
) -> list[float]:
    """
    Convert the public ScoredCluster M3 output into observable features.

    Explicitly excluded:
        - GroundTruth
        - deterministic risk score
        - risk level
        - Gemini output
        - policy decision
    """

    signals = cluster.signals

    sd = signals["shared_device"]
    sn = signals["shared_network"]
    cb = signals["account_creation_burst"]
    tv = signals["transaction_velocity"]
    tc = signals["transaction_coordination"]
    ra = signals["return_anomaly"]
    gc = signals["graph_connectivity"]

    return [
        # --------------------------------------------------------------
        # Graph / infrastructure
        # --------------------------------------------------------------

        safe_float(
            len(cluster.customers)
        ),

        safe_float(
            sd.get("num_devices")
        ),

        safe_float(
            sd.get("max_customers_per_device")
        ),

        safe_float(
            sd.get("shared_device_ratio")
        ),

        safe_float(
            sn.get("num_networks")
        ),

        safe_float(
            sn.get("max_customers_per_network")
        ),

        safe_float(
            sn.get("shared_network_ratio")
        ),

        # --------------------------------------------------------------
        # Account creation / temporal
        # --------------------------------------------------------------

        safe_float(
            cb.get("creation_time_span_hours")
        ),

        safe_float(
            cb.get("max_accounts_in_window")
        ),

        safe_float(
            cb.get("burst_ratio")
        ),

        # --------------------------------------------------------------
        # Transaction velocity
        # --------------------------------------------------------------

        safe_float(
            tv.get("num_transactions")
        ),

        safe_float(
            tv.get("transactions_per_customer")
        ),

        safe_float(
            tv.get("max_transactions_in_window")
        ),

        safe_float(
            tv.get("activity_span_hours")
        ),

        safe_float(
            tv.get("velocity_ratio_vs_baseline")
        ),

        # --------------------------------------------------------------
        # Coordination / amount behavior
        # --------------------------------------------------------------

        safe_float(
            tc.get("temporal_coordination_ratio")
        ),

        safe_float(
            tc.get("amount_coefficient_of_variation")
        ),

        safe_float(
            tc.get("distinct_amounts_shared_across_customers")
        ),

        # --------------------------------------------------------------
        # Return behavior
        # --------------------------------------------------------------

        safe_float(
            ra.get("num_orders")
        ),

        safe_float(
            ra.get("num_returns")
        ),

        safe_float(
            ra.get("return_rate")
        ),

        safe_float(
            ra.get("deviation_ratio")
        ),

        safe_float(
            ra.get("top_customer_return_share")
        ),

        # --------------------------------------------------------------
        # Graph structure
        # --------------------------------------------------------------

        safe_float(
            gc.get("num_customer_nodes")
        ),

        safe_float(
            gc.get("num_device_nodes")
        ),

        safe_float(
            gc.get("num_network_nodes")
        ),

        safe_float(
            gc.get("num_edges")
        ),

        safe_float(
            gc.get("density")
        ),

        safe_float(
            gc.get("avg_customer_degree")
        ),

        safe_float(
            gc.get("diameter")
        ),
    ]


# ----------------------------------------------------------------------
# Ground-truth boundary
# ----------------------------------------------------------------------

async def load_evaluation_labels(
    scored_clusters,
) -> dict[str, int]:
    """
    Load evaluation-only labels.

    GroundTruth never enters feature construction.
    """

    config = RiskConfig()

    async with AsyncSessionLocal() as session:
        ground_truth = await load_ground_truth(
            session
        )

    labels: dict[str, int] = {}

    for cluster in scored_clusters:
        actual = cluster_ground_truth_label(
            cluster,
            ground_truth,
            config,
        )

        if actual is not None:
            labels[
                cluster.cluster_id
            ] = int(actual)

    return labels


# ----------------------------------------------------------------------
# Dataset collection
# ----------------------------------------------------------------------

async def collect_seed(
    seed: int,
    dataset_dir: Path,
) -> list[dict]:
    """
    Generate, load, and score one synthetic seed.

    Returns rows containing:
        seed
        cluster
        features
        label
    """

    print()
    print("=" * 72)
    print(f"COLLECTING SEED {seed}")
    print("=" * 72)

    # Generate isolated CSV dataset.
    generate_seed(
        seed,
        dataset_dir,
    )

    # Reset/load database and dispose stale DB connections.
    await load_seed(
        dataset_dir
    )

    print()
    print("Running M2 + M3 risk pipeline...")
    print()

    async with AsyncSessionLocal() as session:
        scored_clusters = (
            await run_risk_pipeline_async(
                session=session,
            )
        )

    scored_clusters = list(
        scored_clusters
    )

    print(
        f"Candidate clusters: "
        f"{len(scored_clusters)}"
    )

    labels = await load_evaluation_labels(
        scored_clusters
    )

    print(
        f"Clusters with evaluation labels: "
        f"{len(labels)}"
    )

    rows: list[dict] = []

    for cluster in scored_clusters:
        label = labels.get(
            cluster.cluster_id
        )

        if label is None:
            continue

        rows.append(
            {
                "seed": seed,
                "cluster": cluster,
                "features": cluster_to_features(
                    cluster
                ),
                "label": label,
            }
        )

    positives = sum(
        row["label"]
        for row in rows
    )

    print(
        f"Evaluation positives: "
        f"{positives}"
    )

    print(
        f"Evaluation negatives: "
        f"{len(rows) - positives}"
    )

    print(
        f"Feature count: "
        f"{len(FEATURE_NAMES)}"
    )

    return rows


# ----------------------------------------------------------------------
# ML model
# ----------------------------------------------------------------------

def build_model() -> Pipeline:
    """
    Build the same Gradient Boosting configuration used
    for the ML role experiment.
    """

    return Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="median"
                ),
            ),
            (
                "model",
                GradientBoostingClassifier(
                    random_state=RANDOM_SEED,
                    n_estimators=150,
                    learning_rate=0.05,
                    max_depth=3,
                ),
            ),
        ]
    )


# ----------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------

def calculate_metrics(
    y_true: list[int],
    y_pred: list[int],
    probabilities: list[float],
) -> dict:
    """Calculate classification metrics."""

    tn, fp, fn, tp = confusion_matrix(
        y_true,
        y_pred,
        labels=[0, 1],
    ).ravel()

    return {
        "precision": precision_score(
            y_true,
            y_pred,
            zero_division=0,
        ),
        "recall": recall_score(
            y_true,
            y_pred,
            zero_division=0,
        ),
        "f1": f1_score(
            y_true,
            y_pred,
            zero_division=0,
        ),
        "fpr": (
            fp / (fp + tn)
            if (fp + tn)
            else 0.0
        ),
        "roc_auc": (
            roc_auc_score(
                y_true,
                probabilities,
            )
            if len(set(y_true)) > 1
            else float("nan")
        ),
        "pr_auc": (
            average_precision_score(
                y_true,
                probabilities,
            )
            if len(set(y_true)) > 1
            else float("nan")
        ),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


# ----------------------------------------------------------------------
# Held-out evaluation
# ----------------------------------------------------------------------

def evaluate_seed(
    rows: list[dict],
    model: Pipeline,
) -> dict:
    """
    Evaluate ML and deterministic detection on one held-out seed.

    Also evaluates ML candidate prioritization at the top 25% budget.
    """

    X = [
        row["features"]
        for row in rows
    ]

    y = [
        row["label"]
        for row in rows
    ]

    probabilities = (
        model.predict_proba(X)[:, 1]
    )

    ml_predictions = [
        int(
            probability >= ML_THRESHOLD
        )
        for probability in probabilities
    ]

    ml_metrics = calculate_metrics(
        y,
        ml_predictions,
        list(probabilities),
    )

    # --------------------------------------------------------------
    # Deterministic detector
    # --------------------------------------------------------------

    detector_predictions = [
        int(
            float(
                row["cluster"].risk.score
            ) >= DETERMINISTIC_THRESHOLD
        )
        for row in rows
    ]

    detector_probabilities = [
        float(
            row["cluster"].risk.score
        ) / 100.0
        for row in rows
    ]

    detector_metrics = calculate_metrics(
        y,
        detector_predictions,
        detector_probabilities,
    )

    # --------------------------------------------------------------
    # Role B — Candidate prioritization
    # --------------------------------------------------------------

    ranking_rows = []

    for index, row in enumerate(rows):
        ranking_rows.append(
            {
                "cluster_id": (
                    row["cluster"].cluster_id
                ),
                "ml_probability": float(
                    probabilities[index]
                ),
                "truth": row["label"],
            }
        )

    ranking_rows.sort(
        key=lambda item: item[
            "ml_probability"
        ],
        reverse=True,
    )

    top_k = max(
        1,
        math.ceil(
            len(ranking_rows)
            * TOP_K_FRACTION
        ),
    )

    prioritized_rows = ranking_rows[
        :top_k
    ]

    prioritized_true_positives = sum(
        row["truth"]
        for row in prioritized_rows
    )

    total_positives = sum(y)

    prioritization_precision = (
        prioritized_true_positives / top_k
        if top_k
        else 0.0
    )

    prioritization_recall = (
        prioritized_true_positives
        / total_positives
        if total_positives
        else 0.0
    )

    # --------------------------------------------------------------
    # Role C — Secondary validation
    # --------------------------------------------------------------

    disagreements = 0
    disagreement_tp = 0
    disagreement_fp = 0

    for index, row in enumerate(rows):

        detector_prediction = (
            detector_predictions[index]
        )

        ml_prediction = (
            ml_predictions[index]
        )

        if (
            detector_prediction
            != ml_prediction
        ):
            disagreements += 1

            if (
                ml_prediction == 1
                and row["label"] == 1
            ):
                disagreement_tp += 1

            if (
                ml_prediction == 1
                and row["label"] == 0
            ):
                disagreement_fp += 1

    agreement_rate = (
        1.0
        - disagreements / len(rows)
        if rows
        else 1.0
    )

    return {
        "candidate_clusters": len(rows),
        "positives": sum(y),
        "negatives": len(y) - sum(y),

        "ml_precision": ml_metrics[
            "precision"
        ],
        "ml_recall": ml_metrics[
            "recall"
        ],
        "ml_f1": ml_metrics[
            "f1"
        ],
        "ml_fpr": ml_metrics[
            "fpr"
        ],
        "ml_roc_auc": ml_metrics[
            "roc_auc"
        ],
        "ml_pr_auc": ml_metrics[
            "pr_auc"
        ],

        "detector_precision": (
            detector_metrics[
                "precision"
            ]
        ),
        "detector_recall": (
            detector_metrics[
                "recall"
            ]
        ),
        "detector_f1": (
            detector_metrics[
                "f1"
            ]
        ),
        "detector_fpr": (
            detector_metrics[
                "fpr"
            ]
        ),

        "top_k": top_k,

        "prioritization_precision": (
            prioritization_precision
        ),

        "prioritization_recall": (
            prioritization_recall
        ),

        "disagreements": disagreements,

        "agreement_rate": (
            agreement_rate
        ),

        "disagreement_tp": (
            disagreement_tp
        ),

        "disagreement_fp": (
            disagreement_fp
        ),
    }


# ----------------------------------------------------------------------
# Main experiment
# ----------------------------------------------------------------------

async def main() -> None:

    print("=" * 72)
    print(
        "TRUSTGRAPH — ML ROLE MULTISEED EXPERIMENT"
    )
    print("=" * 72)
    print()

    print(
        "Development seeds :",
        DEVELOPMENT_SEEDS,
    )

    print(
        "Held-out seeds    :",
        HELD_OUT_SEEDS,
    )

    print(
        "ML threshold      :",
        ML_THRESHOLD,
    )

    print(
        "Detector threshold:",
        DETERMINISTIC_THRESHOLD,
    )

    print(
        "Top-K fraction    :",
        f"{TOP_K_FRACTION:.0%}",
    )

    print()

    DATA_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_rows: dict[
        int,
        list[dict],
    ] = {}

    try:

        # ----------------------------------------------------------
        # Collect all seeds
        # ----------------------------------------------------------

        for seed in ALL_SEEDS:

            dataset_dir = (
                DATA_ROOT
                / f"seed_{seed}"
            )

            rows = await collect_seed(
                seed,
                dataset_dir,
            )

            all_rows[seed] = rows

        # ----------------------------------------------------------
        # Development training population
        # ----------------------------------------------------------

        development_rows = [
            row
            for seed in DEVELOPMENT_SEEDS
            for row in all_rows[seed]
        ]

        held_out_rows = [
            row
            for seed in HELD_OUT_SEEDS
            for row in all_rows[seed]
        ]

        X_train = [
            row["features"]
            for row in development_rows
        ]

        y_train = [
            row["label"]
            for row in development_rows
        ]

        print()
        print("=" * 72)
        print("TRAINING")
        print("=" * 72)
        print()

        print(
            f"Development clusters : "
            f"{len(development_rows)}"
        )

        print(
            f"Development positives: "
            f"{sum(y_train)}"
        )

        print(
            f"Development negatives: "
            f"{len(y_train) - sum(y_train)}"
        )

        print(
            f"Held-out clusters    : "
            f"{len(held_out_rows)}"
        )

        print(
            f"Held-out positives   : "
            f"{sum(row['label'] for row in held_out_rows)}"
        )

        print()

        if len(set(y_train)) < 2:
            raise RuntimeError(
                "Development population does not "
                "contain both classes."
            )

        print(
            "Training Gradient Boosting..."
        )

        model = build_model()

        model.fit(
            X_train,
            y_train,
        )

        print(
            "Training complete."
        )

        # ----------------------------------------------------------
        # Evaluate held-out seeds
        # ----------------------------------------------------------

        results = []

        print()
        print("=" * 72)
        print("HELD-OUT EVALUATION")
        print("=" * 72)

        for seed in HELD_OUT_SEEDS:

            metrics = evaluate_seed(
                all_rows[seed],
                model,
            )

            metrics["seed"] = seed

            results.append(metrics)

            print()
            print(
                f"SEED {seed}"
            )

            print(
                f"  ML Precision          : "
                f"{metrics['ml_precision']:.4f}"
            )

            print(
                f"  ML Recall             : "
                f"{metrics['ml_recall']:.4f}"
            )

            print(
                f"  ML F1                 : "
                f"{metrics['ml_f1']:.4f}"
            )

            print(
                f"  ML FPR                : "
                f"{metrics['ml_fpr']:.4f}"
            )

            print(
                f"  ML ROC-AUC            : "
                f"{metrics['ml_roc_auc']:.4f}"
            )

            print(
                f"  ML PR-AUC             : "
                f"{metrics['ml_pr_auc']:.4f}"
            )

            print(
                f"  Detector F1           : "
                f"{metrics['detector_f1']:.4f}"
            )

            print(
                f"  Detector Recall       : "
                f"{metrics['detector_recall']:.4f}"
            )

            print(
                f"  Top-K Precision       : "
                f"{metrics['prioritization_precision']:.4f}"
            )

            print(
                f"  Top-K Recall          : "
                f"{metrics['prioritization_recall']:.4f}"
            )

            print(
                f"  Disagreements         : "
                f"{metrics['disagreements']}"
            )

        # ----------------------------------------------------------
        # Aggregate held-out metrics
        # ----------------------------------------------------------

        def mean(
            field: str,
        ) -> float:

            values = [
                float(result[field])
                for result in results
                if math.isfinite(
                    float(result[field])
                )
            ]

            return (
                sum(values) / len(values)
                if values
                else float("nan")
            )

        aggregate = {
            "ml_precision": mean(
                "ml_precision"
            ),
            "ml_recall": mean(
                "ml_recall"
            ),
            "ml_f1": mean(
                "ml_f1"
            ),
            "ml_fpr": mean(
                "ml_fpr"
            ),
            "ml_roc_auc": mean(
                "ml_roc_auc"
            ),
            "ml_pr_auc": mean(
                "ml_pr_auc"
            ),

            "detector_precision": mean(
                "detector_precision"
            ),
            "detector_recall": mean(
                "detector_recall"
            ),
            "detector_f1": mean(
                "detector_f1"
            ),
            "detector_fpr": mean(
                "detector_fpr"
            ),

            "prioritization_precision": mean(
                "prioritization_precision"
            ),
            "prioritization_recall": mean(
                "prioritization_recall"
            ),

            "agreement_rate": mean(
                "agreement_rate"
            ),
        }

        # ----------------------------------------------------------
        # Save CSV
        # ----------------------------------------------------------

        with CSV_PATH.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:

            writer = csv.writer(
                handle
            )

            writer.writerow(
                [
                    "seed",
                    "candidate_clusters",
                    "positives",
                    "negatives",
                    "ml_precision",
                    "ml_recall",
                    "ml_f1",
                    "ml_fpr",
                    "ml_roc_auc",
                    "ml_pr_auc",
                    "detector_precision",
                    "detector_recall",
                    "detector_f1",
                    "detector_fpr",
                    "top_k",
                    "prioritization_precision",
                    "prioritization_recall",
                    "disagreements",
                    "agreement_rate",
                    "disagreement_tp",
                    "disagreement_fp",
                ]
            )

            for result in results:

                writer.writerow(
                    [
                        result["seed"],
                        result[
                            "candidate_clusters"
                        ],
                        result["positives"],
                        result["negatives"],
                        round(
                            result[
                                "ml_precision"
                            ],
                            6,
                        ),
                        round(
                            result[
                                "ml_recall"
                            ],
                            6,
                        ),
                        round(
                            result["ml_f1"],
                            6,
                        ),
                        round(
                            result["ml_fpr"],
                            6,
                        ),
                        round(
                            result[
                                "ml_roc_auc"
                            ],
                            6,
                        ),
                        round(
                            result[
                                "ml_pr_auc"
                            ],
                            6,
                        ),
                        round(
                            result[
                                "detector_precision"
                            ],
                            6,
                        ),
                        round(
                            result[
                                "detector_recall"
                            ],
                            6,
                        ),
                        round(
                            result[
                                "detector_f1"
                            ],
                            6,
                        ),
                        round(
                            result[
                                "detector_fpr"
                            ],
                            6,
                        ),
                        result["top_k"],
                        round(
                            result[
                                "prioritization_precision"
                            ],
                            6,
                        ),
                        round(
                            result[
                                "prioritization_recall"
                            ],
                            6,
                        ),
                        result[
                            "disagreements"
                        ],
                        round(
                            result[
                                "agreement_rate"
                            ],
                            6,
                        ),
                        result[
                            "disagreement_tp"
                        ],
                        result[
                            "disagreement_fp"
                        ],
                    ]
                )

        # ----------------------------------------------------------
        # Save report
        # ----------------------------------------------------------

        report_lines = [
            "# TrustGraph — ML Role Multiseed Experiment",
            "",
            "## Purpose",
            "",
            "LAB-only evaluation of the operational role of the "
            "Gradient Boosting model across unseen synthetic seeds.",
            "",
            "The production TrustGraph pipeline was not modified.",
            "",
            "## Evaluation Design",
            "",
            "Development seeds:",
            "",
            "- 42",
            "- 43",
            "- 44",
            "- 45",
            "- 46",
            "",
            "Held-out seeds:",
            "",
            "- 9001",
            "- 9002",
            "- 9003",
            "- 9004",
            "- 9005",
            "",
            "The model was trained only on the development population "
            "and evaluated only on the held-out population.",
            "",
            "## Ground-Truth Boundary",
            "",
            "Ground truth was obtained exclusively through "
            "`app.risk.evaluation`.",
            "",
            "Ground truth was never included in the ML feature vector.",
            "",
            "The following were also excluded from ML features:",
            "",
            "- deterministic risk score",
            "- risk level",
            "- Gemini output",
            "- policy decision",
            "",
            "## Model",
            "",
            "- Model: Gradient Boosting",
            f"- Feature count: {len(FEATURE_NAMES)}",
            "- Estimators: 150",
            "- Learning rate: 0.05",
            "- Maximum depth: 3",
            f"- ML threshold: {ML_THRESHOLD}",
            f"- Deterministic threshold: "
            f"{DETERMINISTIC_THRESHOLD}",
            "",
            "## Held-Out Results",
            "",
            "| Seed | ML Precision | ML Recall | ML F1 | "
            "ML FPR | Detector F1 | Top-K Precision | "
            "Top-K Recall |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]

        for result in results:

            report_lines.append(
                f"| {result['seed']} "
                f"| {result['ml_precision']:.4f} "
                f"| {result['ml_recall']:.4f} "
                f"| {result['ml_f1']:.4f} "
                f"| {result['ml_fpr']:.4f} "
                f"| {result['detector_f1']:.4f} "
                f"| {result['prioritization_precision']:.4f} "
                f"| {result['prioritization_recall']:.4f} |"
            )

        report_lines.extend(
            [
                "",
                "## Mean Held-Out Performance",
                "",
                f"- ML precision: "
                f"{aggregate['ml_precision']:.4f}",
                f"- ML recall: "
                f"{aggregate['ml_recall']:.4f}",
                f"- ML F1: "
                f"{aggregate['ml_f1']:.4f}",
                f"- ML FPR: "
                f"{aggregate['ml_fpr']:.4f}",
                f"- ML ROC-AUC: "
                f"{aggregate['ml_roc_auc']:.4f}",
                f"- ML PR-AUC: "
                f"{aggregate['ml_pr_auc']:.4f}",
                "",
                f"- Detector precision: "
                f"{aggregate['detector_precision']:.4f}",
                f"- Detector recall: "
                f"{aggregate['detector_recall']:.4f}",
                f"- Detector F1: "
                f"{aggregate['detector_f1']:.4f}",
                f"- Detector FPR: "
                f"{aggregate['detector_fpr']:.4f}",
                "",
                f"- Top-K prioritization precision: "
                f"{aggregate['prioritization_precision']:.4f}",
                f"- Top-K prioritization recall: "
                f"{aggregate['prioritization_recall']:.4f}",
                f"- Mean detector/ML agreement: "
                f"{aggregate['agreement_rate']:.4f}",
                "",
                "## Operational Interpretation",
                "",
                "Role B treats ML as a candidate-prioritization layer "
                "over candidates already generated by deterministic "
                "relationship-first intelligence.",
                "",
                "Role C treats ML/deterministic disagreement as an "
                "uncertainty signal rather than allowing ML to override "
                "deterministic safety controls.",
                "",
                "Neither role changes the deterministic Policy Engine's "
                "authority.",
                "",
                "## Database Isolation / Reproducibility",
                "",
                "Each seed was generated into an isolated dataset "
                "directory and loaded into the LAB database before "
                "running the real M2 + M3 pipeline.",
                "",
                "Because the loader resets the local development schema "
                "between seeds, the SQLAlchemy async engine connection "
                "pool is explicitly disposed after each reset to avoid "
                "stale asyncpg prepared-statement caches.",
                "",
                "The original seed-42 dataset is restored after "
                "completion.",
                "",
                "## Important Limitation",
                "",
                "These are controlled synthetic-data experiments.",
                "",
                "They are not production fraud-detection performance "
                "claims.",
                "",
                "The held-out results should be interpreted together "
                "with the existing deterministic multi-seed validation "
                "and adversarial stress tests.",
                "",
                "## Feature Families",
                "",
                "Features are derived from observable graph, "
                "infrastructure, account-creation, temporal, "
                "transaction, amount, return, and behavioral "
                "measurements.",
                "",
                "## Reproducibility",
                "",
                "Development seeds are used exclusively for training.",
                "",
                "Held-out seeds are never used during model fitting.",
                "",
                "The same 30-feature observable representation and "
                "Gradient Boosting configuration are used across "
                "the experiment.",
                "",
            ]
        )

        REPORT_PATH.write_text(
            "\n".join(
                report_lines
            ),
            encoding="utf-8",
        )

        # ----------------------------------------------------------
        # Console summary
        # ----------------------------------------------------------

        print()
        print("=" * 72)
        print(
            "ML ROLE MULTISEED EXPERIMENT COMPLETE"
        )
        print("=" * 72)
        print()

        print(
            "MEAN HELD-OUT ML"
        )

        print(
            f"  Precision : "
            f"{aggregate['ml_precision']:.4f}"
        )

        print(
            f"  Recall    : "
            f"{aggregate['ml_recall']:.4f}"
        )

        print(
            f"  F1        : "
            f"{aggregate['ml_f1']:.4f}"
        )

        print(
            f"  FPR       : "
            f"{aggregate['ml_fpr']:.4f}"
        )

        print(
            f"  ROC-AUC   : "
            f"{aggregate['ml_roc_auc']:.4f}"
        )

        print(
            f"  PR-AUC    : "
            f"{aggregate['ml_pr_auc']:.4f}"
        )

        print()

        print(
            "MEAN HELD-OUT DETERMINISTIC DETECTOR"
        )

        print(
            f"  Precision : "
            f"{aggregate['detector_precision']:.4f}"
        )

        print(
            f"  Recall    : "
            f"{aggregate['detector_recall']:.4f}"
        )

        print(
            f"  F1        : "
            f"{aggregate['detector_f1']:.4f}"
        )

        print(
            f"  FPR       : "
            f"{aggregate['detector_fpr']:.4f}"
        )

        print()

        print(
            "ROLE B — CANDIDATE PRIORITIZATION"
        )

        print(
            f"  Top-K Precision : "
            f"{aggregate['prioritization_precision']:.4f}"
        )

        print(
            f"  Top-K Recall    : "
            f"{aggregate['prioritization_recall']:.4f}"
        )

        print()

        print(
            "ROLE C — SECONDARY VALIDATION"
        )

        print(
            f"  Mean Agreement  : "
            f"{aggregate['agreement_rate']:.4f}"
        )

        print()

        print(
            f"CSV    : {CSV_PATH}"
        )

        print(
            f"Report : {REPORT_PATH}"
        )

        print()

    finally:

        # ----------------------------------------------------------
        # Always restore seed 42
        # ----------------------------------------------------------

        print()
        print("=" * 72)
        print("RESTORING SEED 42")
        print("=" * 72)
        print()

        try:

            if ORIGINAL_DATA_DIR.exists():

                await load_seed(
                    ORIGINAL_DATA_DIR
                )

                print()
                print(
                    "Seed 42 restoration complete."
                )

            else:

                print(
                    "WARNING: original "
                    "data/synthetic directory "
                    "does not exist; "
                    "restoration skipped."
                )

        except Exception as exc:

            print(
                "WARNING: seed-42 restoration "
                "failed:",
                repr(exc),
            )


if __name__ == "__main__":
    asyncio.run(main())