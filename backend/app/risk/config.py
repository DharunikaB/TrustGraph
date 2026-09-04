"""Configuration for the M3 risk engine.

Every weight, cap, and threshold below was chosen by inspecting the
ACTUAL distribution of M2 signal outputs on the verified 1000-customer
/ 80-candidate-cluster dataset (see the M3 section of README.md for
the full derivation and the raw numbers) -- nothing here is an
arbitrary round number picked in advance.

METHODOLOGY SUMMARY
--------------------
The 100-point budget is split into four evidence categories that
mirror the "relationship + temporal + behavioral + graph" structure
the M3 spec calls for:

    RELATIONSHIP  (max 15) -- shared device / shared network breadth
    TEMPORAL      (max 20) -- account creation burst
    BEHAVIORAL    (max 45) -- velocity (15) + coordination (15) + return anomaly (15)
    GRAPH         (max 20) -- structural redundancy (see below)

RELATIONSHIP is deliberately capped LOW (15/100) even though shared
device/network ratios are 1.0 for most candidate clusters in the
dataset (median 1.0) -- because EVERY M2 candidate cluster is, by
definition of how clustering works, a group of customers connected by
shared infrastructure. Giving this category strong weight would make
"being a candidate cluster at all" the dominant driver of risk, which
directly contradicts the frozen principle that shared device/IP alone
is never abuse. It's included because *degree* of sharing still carries
a little information, but it can never push a cluster's score far on
its own: with zero temporal/behavioral evidence, RELATIONSHIP + GRAPH
alone caps out around 35/100 on this dataset (see README) -- solidly
inside the LOW/MEDIUM range, never HIGH or CRITICAL.

GRAPH uses structural redundancy, not raw density or degree. Average
customer degree turned out to be a constant 2.0 across every cluster
in the dataset (every customer connects to exactly one device node and
one network node in the relationship graph), so it carries no
discriminating information and is excluded. Instead, GRAPH measures
how many independent shared-infrastructure link *types* tie the same
group of customers together: sharing a device only (or an IP only)
produces zero redundancy (the subgraph is a tree); sharing BOTH a
device AND an IP among the same people produces cycles, which the
redundancy ratio captures. This is a genuinely different axis from
RELATIONSHIP's "how much of the cluster is affected" -- it answers
"how many corroborating infrastructure signals exist", not "how many
people share".

TEMPORAL (burst_ratio) and BEHAVIORAL sub-scores are the dataset's
best discriminators (see the threshold-sweep table in README): they
have wide value ranges and don't saturate near 1.0 for nearly every
cluster the way relationship signals do.

Velocity and return-anomaly scores are computed from the EXCESS over
the dataset-wide baseline (M2 already reports each cluster's rate
relative to that baseline), not the raw rate -- so a cluster
transacting/returning at exactly the dataset-average pace scores zero
in that sub-category, and only above-baseline behavior contributes.
Both are capped so one extreme cluster can't single-handedly dominate
its sub-category before other evidence is considered.

Coordination and return-anomaly each reserve a small (3-point)
"supporting evidence" bonus -- repeated identical amounts across
customers, and returns concentrated in one customer, respectively --
exactly matching M2's own framing of amount similarity and return
concentration as supporting-only, never required, evidence.

RISK LEVEL THRESHOLDS were chosen from a precision-at-threshold sweep
against ground truth (evaluation-only; never fed back into scoring):
in the current dataset, the fraction of flagged clusters that are
majority-ground-truth-abuse sits close to the 26% dataset base rate
for scores below ~50, then jumps to 85%+ at score >= 50 and reaches
100% (small n = 6) at score >= 55, staying at 100% (n = 4) above 65.
The band edges below follow that jump. The 100%-precision tail is
based on very few clusters and should NOT be read as "score >= 65
guarantees abuse" -- see the generalization checks in
tests/test_risk.py and the README for the honest caveat.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RiskConfig:
    # --- Category weights (must sum to 100) ---
    relationship_weight: float = 15.0
    temporal_weight: float = 20.0
    velocity_weight: float = 15.0
    coordination_weight: float = 15.0
    return_anomaly_weight: float = 15.0
    graph_weight: float = 20.0

    # --- Sub-category caps / normalization ---
    # Velocity/return scores are based on EXCESS over baseline (ratio - 1),
    # capped before scaling so one extreme cluster can't dominate.
    velocity_excess_cap: float = 2.0
    return_deviation_excess_cap: float = 4.0

    # Coordination: base score from temporal_coordination_ratio (already
    # 0-1), scaled to leave room for the supporting-evidence bonus.
    coordination_base_weight: float = 12.0
    coordination_repeated_amount_bonus: float = 3.0

    # Return anomaly: base score from deviation excess, scaled to leave
    # room for the concentration bonus. Concentration bonus only applies
    # when there are >=2 returns (a single return is trivially "100%
    # from one customer" and would be meaningless supporting evidence).
    return_base_weight: float = 12.0
    return_concentration_bonus: float = 3.0
    return_concentration_min_returns: int = 2

    # --- Risk level bands (0-100 score) ---
    # See module docstring for the precision-sweep derivation.
    low_max: float = 25.0       # [0, 25)
    medium_max: float = 50.0    # [25, 50)
    high_max: float = 65.0      # [50, 65)
    # CRITICAL is [65, 100]

    def risk_level(self, score: float) -> RiskLevel:
        if score < self.low_max:
            return RiskLevel.LOW
        if score < self.medium_max:
            return RiskLevel.MEDIUM
        if score < self.high_max:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    # --- Evaluation ---
    # Default primary threshold for the "flagged vs not flagged" binary
    # decision used in evaluation.py's headline metrics. The final operating
    # point is 52: it was selected from development-seed behavior as a
    # precision-oriented operating point, then checked on untouched seeds.
    # It is an evaluation operating point, not a universal fraud boundary.
    default_evaluation_threshold: float = 52.0
    threshold_sweep: tuple[float, ...] = (20.0, 30.0, 40.0, 50.0, 52.0, 55.0, 60.0, 70.0, 80.0, 90.0)

    # Majority-vote rule for mapping a candidate cluster (which may mix
    # ground-truth labels if customers coincidentally connect) to a
    # single cluster-level ground truth for evaluation purposes.
    cluster_abuse_purity_threshold: float = 0.5
