"""
TrustGraph — ML Role Experiment Harness

LAB-ONLY.

Purpose:
    Determine the most defensible operational role for the previously
    evaluated Gradient Boosting model without modifying TrustGraph's
    production detection, risk, policy, Gemini, API, or frontend paths.

Roles tested:

    A. Risk Augmentation
       ML probability provides a bounded adjustment to deterministic risk.

    B. Candidate Prioritization
       ML probability ranks existing M2/M3 candidate clusters for
       downstream investigation.

    C. Secondary Validation
       ML independently validates the deterministic detector and exposes
       detector/ML disagreement as an uncertainty signal.

Important evaluation boundary:

    M2/M3 never imports GroundTruth.
    This experiment obtains labels ONLY through app.risk.evaluation.
    Ground truth is never included in the ML feature vector.

This is an experimental analysis, not a production scoring change.
"""

from __future__ import annotations

import asyncio
import csv
import math
import random
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

from app.db.session import AsyncSessionLocal
from app.risk.config import RiskConfig
from app.risk.evaluation import (
    cluster_ground_truth_label,
    load_ground_truth,
)
from app.risk.pipeline import run_risk_pipeline_async


# ----------------------------------------------------------------------
# Experiment configuration
# ----------------------------------------------------------------------

RANDOM_SEED = 20260903

DETERMINISTIC_THRESHOLD = 52.0

# Previously selected grouped-validation GBM operating threshold.
ML_THRESHOLD = 0.37

# Experimental bounded risk adjustment.
# ML can contribute at most +/-10 points.
ML_ADJUSTMENT_RANGE = 20.0

# Candidate prioritization budget.
TOP_K_FRACTION = 0.25

OUTPUT_DIR = Path("artifacts/ml_role_experiments")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CSV_PATH = OUTPUT_DIR / "ml_role_comparison.csv"
REPORT_PATH = OUTPUT_DIR / "ML_ROLE_EXPERIMENT.md"


# ----------------------------------------------------------------------
# Exact observable feature family
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


def cluster_to_features(cluster) -> list[float]:
    """
    Convert the public ScoredCluster M3 output into observable ML features.

    Deliberately excluded:
        - GroundTruth
        - deterministic risk score
        - risk level
        - AI output
        - policy decision

    This prevents the model from simply learning the existing deterministic
    decision or receiving future-stage information.
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
        # Graph / infrastructure
        safe_float(len(cluster.customers)),
        safe_float(sd.get("num_devices")),
        safe_float(sd.get("max_customers_per_device")),
        safe_float(sd.get("shared_device_ratio")),
        safe_float(sn.get("num_networks")),
        safe_float(sn.get("max_customers_per_network")),
        safe_float(sn.get("shared_network_ratio")),

        # Account creation / temporal
        safe_float(cb.get("creation_time_span_hours")),
        safe_float(cb.get("max_accounts_in_window")),
        safe_float(cb.get("burst_ratio")),

        # Transaction velocity
        safe_float(tv.get("num_transactions")),
        safe_float(tv.get("transactions_per_customer")),
        safe_float(tv.get("max_transactions_in_window")),
        safe_float(tv.get("activity_span_hours")),
        safe_float(tv.get("velocity_ratio_vs_baseline")),

        # Coordination / amount behavior
        safe_float(tc.get("temporal_coordination_ratio")),
        safe_float(tc.get("amount_coefficient_of_variation")),
        safe_float(tc.get("distinct_amounts_shared_across_customers")),

        # Return behavior
        safe_float(ra.get("num_orders")),
        safe_float(ra.get("num_returns")),
        safe_float(ra.get("return_rate")),
        safe_float(ra.get("deviation_ratio")),
        safe_float(ra.get("top_customer_return_share")),

        # Graph structure
        safe_float(gc.get("num_customer_nodes")),
        safe_float(gc.get("num_device_nodes")),
        safe_float(gc.get("num_network_nodes")),
        safe_float(gc.get("num_edges")),
        safe_float(gc.get("density")),
        safe_float(gc.get("avg_customer_degree")),
        safe_float(gc.get("diameter")),
    ]


# ----------------------------------------------------------------------
# ML model
# ----------------------------------------------------------------------

def build_model() -> Pipeline:
    """
    Gradient Boosting configuration used for the role experiment.

    Missing values are imputed because some legitimate signal measurements
    are intentionally undefined when insufficient observations exist.
    """

    return Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="median"),
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
            roc_auc_score(y_true, probabilities)
            if len(set(y_true)) > 1
            else float("nan")
        ),
        "pr_auc": (
            average_precision_score(y_true, probabilities)
            if len(set(y_true)) > 1
            else float("nan")
        ),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


# ----------------------------------------------------------------------
# Ground-truth boundary
# ----------------------------------------------------------------------

async def load_evaluation_labels(scored_clusters):
    """
    Evaluation-only label loading.

    This function is intentionally separate from feature construction.
    """

    config = RiskConfig()

    async with AsyncSessionLocal() as session:
        ground_truth = await load_ground_truth(session)

    labels: dict[str, int] = {}

    for cluster in scored_clusters:
        actual = cluster_ground_truth_label(
            cluster,
            ground_truth,
            config,
        )

        if actual is not None:
            labels[cluster.cluster_id] = int(actual)

    return labels


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

async def main() -> None:
    print("=" * 72)
    print("TRUSTGRAPH — ML ROLE EXPERIMENT")
    print("=" * 72)
    print()
    print(f"Random seed : {RANDOM_SEED}")
    print()

    # --------------------------------------------------------------
    # M2 + M3
    # --------------------------------------------------------------

    print("Running M2 + M3 risk pipeline...")

    async with AsyncSessionLocal() as session:
        scored_clusters = await run_risk_pipeline_async(
            session=session,
        )

    scored_clusters = list(scored_clusters)

    print(f"Candidate clusters: {len(scored_clusters)}")
    print()

    # --------------------------------------------------------------
    # Evaluation labels
    # --------------------------------------------------------------

    print("Loading evaluation-only ground truth...")

    labels = await load_evaluation_labels(scored_clusters)

    print(
        f"Clusters with evaluation labels: {len(labels)}"
    )

    if not labels:
        raise RuntimeError(
            "No clusters have evaluation labels."
        )

    # --------------------------------------------------------------
    # Build ML dataset
    # --------------------------------------------------------------

    rows = []

    for cluster in scored_clusters:
        label = labels.get(cluster.cluster_id)

        if label is None:
            continue

        rows.append(
            {
                "cluster": cluster,
                "features": cluster_to_features(cluster),
                "label": label,
            }
        )

    X = [row["features"] for row in rows]
    y = [row["label"] for row in rows]

    print(
        f"Feature count      : {len(FEATURE_NAMES)}"
    )
    print(
        f"Evaluation positives: {sum(y)}"
    )
    print(
        f"Evaluation negatives: {len(y) - sum(y)}"
    )
    print()

    if len(set(y)) < 2:
        raise RuntimeError(
            "ML experiment requires both positive and negative labels."
        )

    # --------------------------------------------------------------
    # Controlled deterministic split
    # --------------------------------------------------------------
    #
    # This role experiment is NOT the final multi-seed validation.
    # That validation already exists as a separate artifact.
    #
    # Here we need a training population and an untouched holdout
    # population to compare operational roles.
    # --------------------------------------------------------------

    rng = random.Random(RANDOM_SEED)

    indices = list(range(len(rows)))
    rng.shuffle(indices)

    # 70/30 experiment split.
    split_index = max(
        1,
        min(
            len(indices) - 1,
            int(len(indices) * 0.70),
        ),
    )

    train_idx = indices[:split_index]
    test_idx = indices[split_index:]

    X_train = [X[i] for i in train_idx]
    y_train = [y[i] for i in train_idx]

    X_test = [X[i] for i in test_idx]
    y_test = [y[i] for i in test_idx]

    print(
        f"Training rows      : {len(train_idx)}"
    )
    print(
        f"Holdout rows       : {len(test_idx)}"
    )
    print()

    # --------------------------------------------------------------
    # Train
    # --------------------------------------------------------------

    model = build_model()
    model.fit(
        X_train,
        y_train,
    )

    probabilities = model.predict_proba(
        X_test
    )[:, 1]

    ml_predictions = [
        int(probability >= ML_THRESHOLD)
        for probability in probabilities
    ]

    baseline_ml_metrics = calculate_metrics(
        y_test,
        ml_predictions,
        list(probabilities),
    )

    # --------------------------------------------------------------
    # Role A — Risk Augmentation
    # --------------------------------------------------------------

    augmentation_rows = []

    for position, idx in enumerate(test_idx):
        cluster = rows[idx]["cluster"]
        probability = float(probabilities[position])
        truth = rows[idx]["label"]

        deterministic_score = float(
            cluster.risk.score
        )

        adjusted_score = (
            deterministic_score
            + ML_ADJUSTMENT_RANGE
            * (probability - 0.5)
        )

        adjusted_score = max(
            0.0,
            min(
                100.0,
                adjusted_score,
            ),
        )

        prediction = int(
            adjusted_score >= DETERMINISTIC_THRESHOLD
        )

        augmentation_rows.append(
            {
                "cluster_id": cluster.cluster_id,
                "deterministic_score": deterministic_score,
                "ml_probability": probability,
                "adjusted_score": adjusted_score,
                "prediction": prediction,
                "truth": truth,
            }
        )

    augmentation_true = [
        row["truth"]
        for row in augmentation_rows
    ]

    augmentation_pred = [
        row["prediction"]
        for row in augmentation_rows
    ]

    augmentation_probability = [
        row["adjusted_score"] / 100.0
        for row in augmentation_rows
    ]

    augmentation_metrics = calculate_metrics(
        augmentation_true,
        augmentation_pred,
        augmentation_probability,
    )

    # --------------------------------------------------------------
    # Role B — Candidate Prioritization
    # --------------------------------------------------------------

    ranking_rows = []

    for position, idx in enumerate(test_idx):
        cluster = rows[idx]["cluster"]

        ranking_rows.append(
            {
                "cluster_id": cluster.cluster_id,
                "ml_probability": float(
                    probabilities[position]
                ),
                "risk_score": float(
                    cluster.risk.score
                ),
                "truth": rows[idx]["label"],
            }
        )

    ranking_rows.sort(
        key=lambda row: row["ml_probability"],
        reverse=True,
    )

    top_k = max(
        1,
        math.ceil(
            len(ranking_rows)
            * TOP_K_FRACTION
        ),
    )

    prioritized_rows = ranking_rows[:top_k]

    priority_true_positives = sum(
        row["truth"]
        for row in prioritized_rows
    )

    priority_total_positives = sum(
        y_test
    )

    priority_precision = (
        priority_true_positives / top_k
        if top_k
        else 0.0
    )

    priority_recall = (
        priority_true_positives
        / priority_total_positives
        if priority_total_positives
        else 0.0
    )

    # --------------------------------------------------------------
    # Role C — Secondary Validation
    # --------------------------------------------------------------

    validator_rows = []

    for position, idx in enumerate(test_idx):
        cluster = rows[idx]["cluster"]

        deterministic_prediction = int(
            float(cluster.risk.score)
            >= DETERMINISTIC_THRESHOLD
        )

        ml_prediction = int(
            probabilities[position]
            >= ML_THRESHOLD
        )

        validator_rows.append(
            {
                "cluster_id": cluster.cluster_id,
                "risk_score": float(
                    cluster.risk.score
                ),
                "ml_probability": float(
                    probabilities[position]
                ),
                "detector_prediction": deterministic_prediction,
                "ml_prediction": ml_prediction,
                "agreement": (
                    deterministic_prediction
                    == ml_prediction
                ),
                "truth": rows[idx]["label"],
            }
        )

    disagreements = [
        row
        for row in validator_rows
        if not row["agreement"]
    ]

    # Evaluate detector and ML predictions independently.
    detector_predictions = [
        row["detector_prediction"]
        for row in validator_rows
    ]

    validator_ml_predictions = [
        row["ml_prediction"]
        for row in validator_rows
    ]

    validator_true = [
        row["truth"]
        for row in validator_rows
    ]

    validator_probabilities = [
        row["ml_probability"]
        for row in validator_rows
    ]

    detector_probabilities = [
        row["risk_score"] / 100.0
        for row in validator_rows
    ]

    detector_metrics = calculate_metrics(
        validator_true,
        detector_predictions,
        detector_probabilities,
    )

    validator_ml_metrics = calculate_metrics(
        validator_true,
        validator_ml_predictions,
        validator_probabilities,
    )

    # --------------------------------------------------------------
    # Save CSV
    # --------------------------------------------------------------

    augmentation_lookup = {
        row["cluster_id"]: row
        for row in augmentation_rows
    }

    validator_lookup = {
        row["cluster_id"]: row
        for row in validator_rows
    }

    with CSV_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.writer(handle)

        writer.writerow(
            [
                "cluster_id",
                "truth",
                "deterministic_score",
                "ml_probability",
                "ml_prediction",
                "augmentation_score",
                "augmentation_prediction",
                "detector_prediction",
                "detector_ml_agreement",
            ]
        )

        for row in ranking_rows:
            cluster_id = row["cluster_id"]

            augmentation = augmentation_lookup[
                cluster_id
            ]

            validator = validator_lookup[
                cluster_id
            ]

            writer.writerow(
                [
                    cluster_id,
                    row["truth"],
                    round(
                        row["risk_score"],
                        4,
                    ),
                    round(
                        row["ml_probability"],
                        6,
                    ),
                    validator[
                        "ml_prediction"
                    ],
                    round(
                        augmentation[
                            "adjusted_score"
                        ],
                        4,
                    ),
                    augmentation[
                        "prediction"
                    ],
                    validator[
                        "detector_prediction"
                    ],
                    validator[
                        "agreement"
                    ],
                ]
            )

    # --------------------------------------------------------------
    # Report
    # --------------------------------------------------------------

    agreement_rate = (
        1.0
        - len(disagreements)
        / len(validator_rows)
    )

    report_lines = [
        "# TrustGraph — ML Role Experiment",
        "",
        "## Purpose",
        "",
        "LAB-only evaluation of three possible operational roles for "
        "the previously evaluated Gradient Boosting model.",
        "",
        "The production TrustGraph pipeline was not modified.",
        "",
        "Roles:",
        "",
        "1. Risk augmentation",
        "2. Candidate prioritization",
        "3. Secondary validation",
        "",
        "Ground truth was obtained exclusively through "
        "`app.risk.evaluation` and was never included in the ML "
        "feature vector.",
        "",
        "## Important Evaluation Note",
        "",
        "This experiment uses a controlled 70/30 training/holdout split "
        "of the current labelled candidate-cluster population.",
        "It is NOT a replacement for the previously generated "
        "multi-seed grouped validation.",
        "",
        "The multi-seed validation remains the authoritative evidence "
        "for generalization.",
        "",
        "## Model",
        "",
        "- Model: Gradient Boosting",
        f"- Feature count: {len(FEATURE_NAMES)}",
        f"- ML threshold: {ML_THRESHOLD}",
        f"- Deterministic risk threshold: {DETERMINISTIC_THRESHOLD}",
        f"- Random seed: {RANDOM_SEED}",
        "",
        "## Baseline ML Holdout",
        "",
        f"- Precision: {baseline_ml_metrics['precision']:.4f}",
        f"- Recall: {baseline_ml_metrics['recall']:.4f}",
        f"- F1: {baseline_ml_metrics['f1']:.4f}",
        f"- FPR: {baseline_ml_metrics['fpr']:.4f}",
        f"- ROC-AUC: {baseline_ml_metrics['roc_auc']:.4f}",
        f"- PR-AUC: {baseline_ml_metrics['pr_auc']:.4f}",
        "",
        "## Role A — Risk Augmentation",
        "",
        "Experimental formula:",
        "",
        "`adjusted_score = deterministic_score + "
        "20 * (ML_probability - 0.5)`",
        "",
        "The adjustment is bounded to +/-10 risk points.",
        "",
        f"- Precision: {augmentation_metrics['precision']:.4f}",
        f"- Recall: {augmentation_metrics['recall']:.4f}",
        f"- F1: {augmentation_metrics['f1']:.4f}",
        f"- FPR: {augmentation_metrics['fpr']:.4f}",
        "",
        "This formula is experimental and is not automatically "
        "promoted into the production risk engine.",
        "",
        "## Role B — Candidate Prioritization",
        "",
        f"- Prioritization budget: {TOP_K_FRACTION:.0%}",
        f"- Candidates prioritized: {top_k}",
        f"- Precision among prioritized candidates: "
        f"{priority_precision:.4f}",
        f"- Recall among prioritized candidates: "
        f"{priority_recall:.4f}",
        "",
        "This role treats ML as an investigation-ranking layer "
        "rather than as the final risk authority.",
        "",
        "## Role C — Secondary Validation",
        "",
        f"- Detector precision: {detector_metrics['precision']:.4f}",
        f"- Detector recall: {detector_metrics['recall']:.4f}",
        f"- Detector F1: {detector_metrics['f1']:.4f}",
        f"- ML precision: {validator_ml_metrics['precision']:.4f}",
        f"- ML recall: {validator_ml_metrics['recall']:.4f}",
        f"- ML F1: {validator_ml_metrics['f1']:.4f}",
        f"- Detector/ML disagreements: {len(disagreements)}",
        f"- Agreement rate: {agreement_rate:.4f}",
        "",
        "Disagreement is treated as an uncertainty signal for "
        "additional investigation rather than as permission for ML "
        "to override deterministic safety controls.",
        "",
        "## Interpretation",
        "",
        "These results are controlled synthetic-data experiments.",
        "They are not production fraud-detection performance claims.",
        "",
        "The final ML role should be selected using:",
        "",
        "- held-out performance",
        "- false-positive behavior",
        "- operational usefulness",
        "- robustness under adversarial testing",
        "- compatibility with deterministic safety controls",
        "",
        "The existing multi-seed validation and adversarial experiments "
        "remain separate evidence artifacts.",
        "",
        "## Feature Families",
        "",
        "Features are derived from observable graph, infrastructure, "
        "account-creation, temporal, transaction, amount, return, "
        "and behavioral measurements.",
        "",
        "Excluded from features:",
        "",
        "- GroundTruth",
        "- deterministic risk score",
        "- risk level",
        "- Gemini output",
        "- policy decision",
        "",
    ]

    REPORT_PATH.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    # --------------------------------------------------------------
    # Console summary
    # --------------------------------------------------------------

    print("=" * 72)
    print("ML ROLE EXPERIMENT COMPLETE")
    print("=" * 72)
    print()

    print("BASELINE ML")
    print(
        f"  Precision : {baseline_ml_metrics['precision']:.4f}"
    )
    print(
        f"  Recall    : {baseline_ml_metrics['recall']:.4f}"
    )
    print(
        f"  F1        : {baseline_ml_metrics['f1']:.4f}"
    )
    print(
        f"  FPR       : {baseline_ml_metrics['fpr']:.4f}"
    )
    print(
        f"  ROC-AUC   : {baseline_ml_metrics['roc_auc']:.4f}"
    )
    print(
        f"  PR-AUC    : {baseline_ml_metrics['pr_auc']:.4f}"
    )
    print()

    print("ROLE A — RISK AUGMENTATION")
    print(
        f"  Precision : {augmentation_metrics['precision']:.4f}"
    )
    print(
        f"  Recall    : {augmentation_metrics['recall']:.4f}"
    )
    print(
        f"  F1        : {augmentation_metrics['f1']:.4f}"
    )
    print(
        f"  FPR       : {augmentation_metrics['fpr']:.4f}"
    )
    print()

    print("ROLE B — CANDIDATE PRIORITIZATION")
    print(
        f"  Top-K     : {top_k}/{len(ranking_rows)}"
    )
    print(
        f"  Precision : {priority_precision:.4f}"
    )
    print(
        f"  Recall    : {priority_recall:.4f}"
    )
    print()

    print("ROLE C — SECONDARY VALIDATION")
    print(
        f"  Detector precision : "
        f"{detector_metrics['precision']:.4f}"
    )
    print(
        f"  Detector recall    : "
        f"{detector_metrics['recall']:.4f}"
    )
    print(
        f"  Detector F1        : "
        f"{detector_metrics['f1']:.4f}"
    )
    print(
        f"  ML precision       : "
        f"{validator_ml_metrics['precision']:.4f}"
    )
    print(
        f"  ML recall          : "
        f"{validator_ml_metrics['recall']:.4f}"
    )
    print(
        f"  ML F1              : "
        f"{validator_ml_metrics['f1']:.4f}"
    )
    print(
        f"  Disagreements      : "
        f"{len(disagreements)}"
    )
    print(
        f"  Agreement          : "
        f"{agreement_rate:.4f}"
    )
    print()

    print(f"CSV    : {CSV_PATH}")
    print(f"Report : {REPORT_PATH}")
    print()


if __name__ == "__main__":
    asyncio.run(main())