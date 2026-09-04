"""Configuration for the M2 intelligence pipeline.

Every time window, threshold, and cutoff used anywhere in the seven
signal families lives here. Nothing in `signals.py`, `clustering.py`,
or `graph_builder.py` should have a bare numeric literal controlling
behavior -- if a magic number shows up in signal logic, it belongs
here instead.

None of these values encode a decision boundary ("above X = abuse").
They only control what gets *measured* and how (window sizes, bin
sizes, minimum group size to bother analyzing). Turning measurements
into a verdict is explicitly out of scope for M2 -- see the module
docstring in `pipeline.py`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IntelligenceConfig:
    # --- Candidate clustering ---
    # A connected component of fewer than this many customers isn't a
    # "cluster" in any meaningful relationship sense -- an isolated
    # customer has no shared-infrastructure evidence to evaluate.
    min_cluster_size: int = 2

    # --- Signal 3: account creation burst ---
    # Sliding window (hours) used to find the densest run of account
    # creations within a cluster.
    creation_burst_window_hours: float = 48.0

    # --- Signal 4: transaction velocity ---
    # Sliding window (hours) used to find the densest run of
    # transactions within a cluster.
    velocity_window_hours: float = 24.0

    # --- Signal 5: transaction coordination ---
    # Two transactions (from different customers in the same cluster)
    # count as "temporally proximate" if they fall within this many
    # minutes of each other.
    coordination_proximity_minutes: float = 60.0
    # Relative amount difference (approximately) below which two transaction
    # amounts are considered "similar". This is supporting evidence only,
    # never a requirement. The small tolerance is intentional: experiments
    # showed broader tolerances increase false positives disproportionately.
    amount_similarity_tolerance: float = 0.005

    # --- Signal 6: return anomaly ---
    # Minimum number of orders a cluster needs before its return rate
    # is considered meaningful enough to compare against baseline
    # (avoids "1 order, 1 return = 100%" noise on tiny clusters).
    min_orders_for_return_rate: int = 3

    # --- Evidence text generation ---
    # Thresholds purely for deciding whether a metric is *worth
    # mentioning* in the human-readable evidence list -- these do NOT
    # feed into any score and have no bearing on detection itself.
    evidence_burst_ratio_threshold: float = 0.6
    evidence_velocity_ratio_threshold: float = 2.0
    evidence_return_rate_multiple_threshold: float = 2.0
    evidence_coordination_ratio_threshold: float = 0.5
