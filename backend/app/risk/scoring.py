"""Transparent, deterministic risk scoring from M2 evidence.

Consumes the `signals` dict M2's `pipeline.run_pipeline` already
produces for each candidate cluster -- no graph construction, no
signal recomputation. If a required field is missing, that's a
contract mismatch with M2 and should fail loudly, not be silently
patched around here.

See `config.py` for the full weighting methodology and its derivation.
"""

from __future__ import annotations

from app.risk.config import RiskConfig
from app.risk.models import Contributor, RiskAssessment


def _relationship_contribution(signals: dict, config: RiskConfig) -> Contributor:
    device_ratio = signals["shared_device"]["shared_device_ratio"]
    network_ratio = signals["shared_network"]["shared_network_ratio"]
    breadth = 0.5 * device_ratio + 0.5 * network_ratio
    contribution = round(breadth * config.relationship_weight, 2)

    return Contributor(
        signal="shared_device_and_network",
        contribution=contribution,
        max_contribution=config.relationship_weight,
        evidence=(
            f"Shared-device ratio {device_ratio:.2f}, shared-network ratio {network_ratio:.2f} "
            f"across the cluster. Sharing infrastructure alone is capped low (max "
            f"{config.relationship_weight:.0f} points) since every M2 candidate cluster is "
            f"defined by shared infrastructure -- this cannot by itself drive a high score."
        ),
    )


def _temporal_contribution(signals: dict, config: RiskConfig) -> Contributor:
    burst = signals["account_creation_burst"]
    burst_ratio = burst["burst_ratio"]
    contribution = round(burst_ratio * config.temporal_weight, 2)

    return Contributor(
        signal="account_creation_burst",
        contribution=contribution,
        max_contribution=config.temporal_weight,
        evidence=(
            f"{burst['max_accounts_in_window']} of {burst['num_customers']} accounts "
            f"created within a single {burst['window_hours']}h window "
            f"(burst ratio {burst_ratio:.2f})."
        ),
    )


def _velocity_contribution(signals: dict, config: RiskConfig) -> Contributor:
    velocity = signals["transaction_velocity"]
    ratio = velocity["velocity_ratio_vs_baseline"]

    if ratio is None or velocity["num_transactions"] == 0:
        return Contributor(
            signal="transaction_velocity",
            contribution=0.0,
            max_contribution=config.velocity_weight,
            evidence="No transactions (or no baseline available) -- no velocity evidence.",
        )

    excess = max(0.0, ratio - 1.0)
    capped_excess = min(excess, config.velocity_excess_cap)
    contribution = round((capped_excess / config.velocity_excess_cap) * config.velocity_weight, 2)

    return Contributor(
        signal="transaction_velocity",
        contribution=contribution,
        max_contribution=config.velocity_weight,
        evidence=(
            f"Transaction rate is {ratio:.2f}x the dataset-wide average "
            f"({velocity['transactions_per_customer']:.2f} vs "
            f"{velocity['baseline_transactions_per_customer']:.2f} per customer). "
            f"Only the excess above baseline (capped at {config.velocity_excess_cap:.1f}x) contributes."
        ),
    )


def _coordination_contribution(signals: dict, config: RiskConfig) -> Contributor:
    coordination = signals["transaction_coordination"]
    ratio = coordination["temporal_coordination_ratio"]
    repeated_amounts = coordination["distinct_amounts_shared_across_customers"]

    base = ratio * config.coordination_base_weight
    bonus = config.coordination_repeated_amount_bonus if repeated_amounts > 0 else 0.0
    contribution = round(min(base + bonus, config.coordination_weight), 2)

    evidence = (
        f"{ratio:.0%} of this cluster's transactions occur within "
        f"{coordination['proximity_window_minutes']:.0f} minutes of another cluster "
        f"member's transaction (timing-based, independent of amount)."
    )
    if repeated_amounts > 0:
        evidence += (
            f" +{config.coordination_repeated_amount_bonus:.0f}pt supporting bonus: "
            f"{repeated_amounts} amount(s) reused across customers."
        )

    return Contributor(
        signal="transaction_coordination",
        contribution=contribution,
        max_contribution=config.coordination_weight,
        evidence=evidence,
    )


def _return_anomaly_contribution(signals: dict, config: RiskConfig) -> Contributor:
    returns = signals["return_anomaly"]

    if returns["insufficient_data"] or returns["deviation_ratio"] is None:
        return Contributor(
            signal="return_anomaly",
            contribution=0.0,
            max_contribution=config.return_anomaly_weight,
            evidence=(
                f"Only {returns['num_orders']} order(s) -- too few to compute a "
                f"meaningful return-rate deviation."
            ),
        )

    deviation = returns["deviation_ratio"]
    excess = max(0.0, deviation - 1.0)
    capped_excess = min(excess, config.return_deviation_excess_cap)
    base = (capped_excess / config.return_deviation_excess_cap) * config.return_base_weight

    bonus = 0.0
    top_share = returns["top_customer_return_share"]
    if returns["num_returns"] >= config.return_concentration_min_returns and top_share is not None:
        bonus = top_share * config.return_concentration_bonus

    contribution = round(min(base + bonus, config.return_anomaly_weight), 2)

    evidence = (
        f"Return rate {returns['return_rate']:.1%} is {deviation:.2f}x the dataset "
        f"baseline ({returns['baseline_return_rate']:.1%})."
    )
    if bonus > 0:
        evidence += (
            f" +{bonus:.1f}pt concentration bonus: {top_share:.0%} of returns come "
            f"from a single customer."
        )

    return Contributor(
        signal="return_anomaly",
        contribution=contribution,
        max_contribution=config.return_anomaly_weight,
        evidence=evidence,
    )


def _graph_contribution(signals: dict, config: RiskConfig) -> Contributor:
    graph = signals["graph_connectivity"]
    total_nodes = (
        graph["num_customer_nodes"] + graph["num_device_nodes"] + graph["num_network_nodes"]
    )
    # Cyclomatic redundancy: edges beyond what a minimal spanning tree
    # would need. Zero when the cluster shares only ONE infrastructure
    # type (e.g. device only); positive when customers are tied together
    # by MORE THAN ONE independent shared-infra type (device AND network),
    # which is stronger corroborating structure than either alone.
    redundancy = graph["num_edges"] - (total_nodes - 1) if total_nodes > 0 else 0
    denominator = max(1, graph["num_customer_nodes"] - 1)
    redundancy_ratio = max(0.0, redundancy / denominator)
    capped_ratio = min(redundancy_ratio, 1.0)
    contribution = round(capped_ratio * config.graph_weight, 2)

    return Contributor(
        signal="graph_connectivity",
        contribution=contribution,
        max_contribution=config.graph_weight,
        evidence=(
            f"Structural redundancy ratio {redundancy_ratio:.2f} -- how many independent "
            f"shared-infrastructure link types (device, network) connect the same "
            f"{graph['num_customer_nodes']} customers, beyond a single minimal link."
        ),
    )


def compute_risk_assessment(signals: dict, config: RiskConfig | None = None) -> RiskAssessment:
    """Compute the full risk assessment for one M2 cluster's signal dict."""
    config = config or RiskConfig()

    contributors = [
        _relationship_contribution(signals, config),
        _temporal_contribution(signals, config),
        _velocity_contribution(signals, config),
        _coordination_contribution(signals, config),
        _return_anomaly_contribution(signals, config),
        _graph_contribution(signals, config),
    ]

    total = sum(c.contribution for c in contributors)
    score = round(min(100.0, max(0.0, total)), 2)
    level = config.risk_level(score)

    return RiskAssessment(score=score, level=level, contributors=contributors)
