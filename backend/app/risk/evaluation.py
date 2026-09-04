"""M3 evaluation -- the EVALUATION path, strictly separate from detection.

    Prediction (from pipeline.py, which NEVER sees ground truth)
        +
    Ground truth (loaded ONLY here)
        ↓
    Metrics

This is the only module in the entire project allowed to import
`GroundTruth`. `app/risk/pipeline.py`, `app/risk/scoring.py`, and
everything in `app/intelligence/` must never import from here or from
`app.models.GroundTruth` -- that boundary is what keeps M3's risk
scores honest. See `test_ground_truth_never_imported_by_detection_path`
in `tests/test_risk.py` for the automated check.

CLUSTER-LEVEL VS CUSTOMER-LEVEL EVALUATION
-------------------------------------------
M2 candidate clusters and M1 ground truth operate at different
granularities, and conflating them silently would produce misleading
numbers. This module evaluates at BOTH levels, explicitly:

- CLUSTER-LEVEL: the unit of evaluation is one of M2's ~80 candidate
  clusters. A cluster's ground-truth label is the MAJORITY vote among
  its member customers' `is_abuse` flags (>= `cluster_abuse_purity_threshold`,
  default 50%) -- most candidate clusters in this dataset are 100% pure
  one way or the other (M1's generator uses independent device/IP pools
  per scenario), but majority vote handles the rare coincidental-overlap
  case without silently mislabeling it. A cluster "counts" as predicted
  abuse if its risk score is >= the evaluation threshold.

  IMPORTANT LIMITATION: cluster-level evaluation only covers customers
  who appear in SOME candidate cluster. In this dataset, most `normal`
  customers have their own unique device and IP and are therefore
  isolated (no candidate cluster at all) -- they are simply absent from
  cluster-level evaluation, not counted as correctly-rejected negatives.

- CUSTOMER-LEVEL: the unit of evaluation is every customer with a
  ground-truth label (all ~1000). A customer counts as "predicted
  abuse" if they belong to ANY candidate cluster whose risk score is
  >= the threshold; a customer who was never even a candidate (isolated,
  no shared device/network) is automatically "not predicted", which is
  the correct behavior for a system that only investigates relationship
  evidence -- but it does mean recall at customer level is capped by
  how many abuse-ring members M2 actually clustered in the first place.

Both are reported. Neither should be read in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GroundTruth
from app.risk.config import RiskConfig
from app.risk.models import ScoredCluster


# ----------------------------------------------------------------------
# Ground truth loading -- the ONLY function in the project allowed to
# query GroundTruth.
# ----------------------------------------------------------------------
async def load_ground_truth(session: AsyncSession) -> dict[str, bool]:
    """customer_id -> is_abuse. EVALUATION-ONLY -- never call from detection code."""
    rows = (await session.execute(select(GroundTruth))).scalars().all()
    return {row.customer_id: row.is_abuse for row in rows}


# ----------------------------------------------------------------------
# Confusion matrix
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class ConfusionMatrix:
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int

    @property
    def precision(self) -> float | None:
        denom = self.true_positives + self.false_positives
        return round(self.true_positives / denom, 4) if denom > 0 else None

    @property
    def recall(self) -> float | None:
        denom = self.true_positives + self.false_negatives
        return round(self.true_positives / denom, 4) if denom > 0 else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return round(2 * p * r / (p + r), 4)

    @property
    def accuracy(self) -> float | None:
        total = self.true_positives + self.false_positives + self.true_negatives + self.false_negatives
        return round((self.true_positives + self.true_negatives) / total, 4) if total > 0 else None

    @property
    def false_positive_rate(self) -> float | None:
        denom = self.false_positives + self.true_negatives
        return round(self.false_positives / denom, 4) if denom > 0 else None

    def as_dict(self) -> dict:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "accuracy": self.accuracy,
            "false_positive_rate": self.false_positive_rate,
        }


# ----------------------------------------------------------------------
# Cluster-level ground truth mapping
# ----------------------------------------------------------------------
def cluster_ground_truth_label(
    cluster: ScoredCluster, ground_truth: dict[str, bool], config: RiskConfig
) -> bool | None:
    """Majority-vote ground truth for a cluster. None if no member has a label."""
    labels = [ground_truth[cid] for cid in cluster.customers if cid in ground_truth]
    if not labels:
        return None
    abuse_fraction = sum(labels) / len(labels)
    return abuse_fraction >= config.cluster_abuse_purity_threshold


# ----------------------------------------------------------------------
# Confusion matrices at each granularity
# ----------------------------------------------------------------------
def cluster_level_confusion_matrix(
    scored_clusters: list[ScoredCluster],
    ground_truth: dict[str, bool],
    threshold: float,
    config: RiskConfig,
) -> ConfusionMatrix:
    tp = fp = tn = fn = 0
    for cluster in scored_clusters:
        actual = cluster_ground_truth_label(cluster, ground_truth, config)
        if actual is None:
            continue  # no ground truth info for any member -- excluded, not guessed
        predicted = cluster.risk.score >= threshold
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1
    return ConfusionMatrix(tp, fp, tn, fn)


def customer_level_confusion_matrix(
    scored_clusters: list[ScoredCluster], ground_truth: dict[str, bool], threshold: float
) -> ConfusionMatrix:
    flagged_customers: set[str] = set()
    for cluster in scored_clusters:
        if cluster.risk.score >= threshold:
            flagged_customers.update(cluster.customers)

    tp = fp = tn = fn = 0
    for customer_id, is_abuse in ground_truth.items():
        predicted = customer_id in flagged_customers
        if predicted and is_abuse:
            tp += 1
        elif predicted and not is_abuse:
            fp += 1
        elif not predicted and is_abuse:
            fn += 1
        else:
            tn += 1
    return ConfusionMatrix(tp, fp, tn, fn)


# ----------------------------------------------------------------------
# Threshold sweep (also usable as PR-curve / ROC-curve source data --
# precision+recall give the PR curve; false_positive_rate+recall give
# the ROC curve, both derivable from the same sweep without recomputation)
# ----------------------------------------------------------------------
def threshold_sweep(
    scored_clusters: list[ScoredCluster],
    ground_truth: dict[str, bool],
    config: RiskConfig,
    level: str = "cluster",
) -> list[dict]:
    if level not in ("cluster", "customer"):
        raise ValueError(f"level must be 'cluster' or 'customer', got {level!r}")

    results = []
    for threshold in config.threshold_sweep:
        cm = (
            cluster_level_confusion_matrix(scored_clusters, ground_truth, threshold, config)
            if level == "cluster"
            else customer_level_confusion_matrix(scored_clusters, ground_truth, threshold)
        )
        results.append({"threshold": threshold, **cm.as_dict()})
    return results


# ----------------------------------------------------------------------
# False-positive financial cost
# ----------------------------------------------------------------------
def false_positive_financial_cost(
    scored_clusters: list[ScoredCluster],
    ground_truth: dict[str, bool],
    threshold: float,
    config: RiskConfig,
) -> dict:
    """Financial context for clusters flagged at `threshold` that are
    actually (majority) legitimate by ground truth.

    Deliberately reports "associated legitimate transaction value", NOT
    a dollar/rupee fraud-prevention-cost figure -- there's no
    justifiable universal cost-per-false-positive assumption available
    from this synthetic dataset. A real deployment would need its own
    cost model (support burden, customer churn risk, chargeback
    handling cost, etc.) plugged in here; this only reports the
    underlying financial facts a cost model would need.
    """
    flagged = [c for c in scored_clusters if c.risk.score >= threshold]
    false_positive_clusters = [
        c for c in flagged if cluster_ground_truth_label(c, ground_truth, config) is False
    ]

    total_flagged = len(flagged)
    fp_count = len(false_positive_clusters)
    fp_rate = round(fp_count / total_flagged, 4) if total_flagged > 0 else None

    legitimate_transaction_value = sum(c.exposure.transaction_value for c in false_positive_clusters)
    legitimate_returned_value = sum(c.exposure.returned_value for c in false_positive_clusters)

    return {
        "threshold": threshold,
        "total_flagged_clusters": total_flagged,
        "false_positive_cluster_count": fp_count,
        "false_positive_rate_among_flagged": fp_rate,
        "associated_legitimate_transaction_value": round(legitimate_transaction_value, 2),
        "associated_legitimate_returned_value": round(legitimate_returned_value, 2),
        "note": (
            "These figures are legitimate customers' transaction/returned values that "
            "would be incorrectly flagged at this threshold -- an operational-impact "
            "measure, NOT a fraud-loss or cost-savings estimate. No universal cost model "
            "is assumed; see README for discussion."
        ),
    }


# ----------------------------------------------------------------------
# Full evaluation report
# ----------------------------------------------------------------------
def evaluate(
    scored_clusters: list[ScoredCluster],
    ground_truth: dict[str, bool],
    config: RiskConfig | None = None,
) -> dict:
    config = config or RiskConfig()
    threshold = config.default_evaluation_threshold

    cluster_cm = cluster_level_confusion_matrix(scored_clusters, ground_truth, threshold, config)
    customer_cm = customer_level_confusion_matrix(scored_clusters, ground_truth, threshold)
    fp_cost = false_positive_financial_cost(scored_clusters, ground_truth, threshold, config)

    flagged_transaction_value = sum(
        c.exposure.transaction_value for c in scored_clusters if c.risk.score >= threshold
    )

    return {
        "evaluation_threshold": threshold,
        "cluster_level": cluster_cm.as_dict(),
        "customer_level": customer_cm.as_dict(),
        "threshold_sweep_cluster_level": threshold_sweep(scored_clusters, ground_truth, config, "cluster"),
        "threshold_sweep_customer_level": threshold_sweep(scored_clusters, ground_truth, config, "customer"),
        "false_positive_financial_cost": fp_cost,
        "summary": {
            "num_candidate_clusters": len(scored_clusters),
            "num_detected_abuse_clusters": cluster_cm.true_positives,
            "num_legitimate_clusters_flagged": cluster_cm.false_positives,
            "cluster_detection_rate": cluster_cm.recall,
            "customer_detection_rate": customer_cm.recall,
            "total_flagged_transaction_value": round(flagged_transaction_value, 2),
        },
        "methodology_notes": [
            "Cluster-level evaluation covers only customers who appear in a candidate "
            "cluster; isolated customers (no shared device/network) are absent from it.",
            "Customer-level evaluation covers all customers with ground truth, including "
            "those never clustered -- they are correctly treated as 'not predicted'.",
            f"Cluster ground truth uses majority vote (>= {config.cluster_abuse_purity_threshold:.0%} "
            "of members labelled abuse) since a candidate cluster can rarely mix ground-truth "
            "categories via coincidental shared-infrastructure overlap.",
        ],
    }
