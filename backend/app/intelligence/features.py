"""Turns raw signal measurements into the structured evidence dict M3 consumes.

`build_evidence_strings` produces human-readable, purely DESCRIPTIVE
statements ("40% of accounts were created within a 6-hour window") --
never verdicts ("this looks like abuse"). The thresholds in
`IntelligenceConfig` used here only decide whether a measurement is
*notable enough to mention*, not whether the cluster is abusive.
"""

from __future__ import annotations

from app.intelligence.config import IntelligenceConfig


def build_evidence_strings(signals: dict, config: IntelligenceConfig) -> list[str]:
    evidence: list[str] = []

    sd = signals["shared_device"]
    if sd["num_devices"] > 0:
        evidence.append(
            f"{sd['num_devices']} device(s) connect customers within this cluster; "
            f"the most-shared device is used by {sd['max_customers_per_device']} customer(s) in this cluster."
        )

    sn = signals["shared_network"]
    if sn["num_networks"] > 0:
        evidence.append(
            f"{sn['num_networks']} network identifier(s) connect customers within this cluster; "
            f"the most-shared network is used by {sn['max_customers_per_network']} customer(s) in this cluster."
        )

    cb = signals["account_creation_burst"]
    if cb["num_customers"] >= 2:
        evidence.append(
            f"Accounts were created over a {cb['creation_time_span_hours']}h span; "
            f"{cb['max_accounts_in_window']} of {cb['num_customers']} were created within "
            f"a single {cb['window_hours']}h window (burst ratio {cb['burst_ratio']})."
        )
        if cb["burst_ratio"] >= config.evidence_burst_ratio_threshold:
            evidence.append(
                f"Account creation is concentrated: {cb['burst_ratio'] * 100:.0f}% of this "
                f"cluster's accounts were created within a single {cb['window_hours']}-hour window."
            )

    tv = signals["transaction_velocity"]
    if tv["num_transactions"] > 0:
        evidence.append(
            f"{tv['num_transactions']} transaction(s) recorded, "
            f"{tv['transactions_per_customer']} per customer on average "
            f"(dataset-wide average: {tv['baseline_transactions_per_customer']})."
        )
        if (
            tv["velocity_ratio_vs_baseline"] is not None
            and tv["velocity_ratio_vs_baseline"] >= config.evidence_velocity_ratio_threshold
        ):
            evidence.append(
                f"Transaction rate per customer is {tv['velocity_ratio_vs_baseline']}x "
                f"the dataset-wide average."
            )

    tc = signals["transaction_coordination"]
    if tc["num_transactions"] >= 2:
        evidence.append(
            f"{tc['temporal_coordination_ratio'] * 100:.0f}% of this cluster's transactions occur "
            f"within {tc['proximity_window_minutes']} minutes of another cluster member's transaction."
        )
        if (
            tc["temporal_coordination_ratio"] >= config.evidence_coordination_ratio_threshold
        ):
            evidence.append(
                "Transaction timing across cluster members is notably coordinated, "
                "independent of whether amounts match."
            )
        if tc["amount_coefficient_of_variation"] is not None:
            evidence.append(
                f"Transaction amount variability (coefficient of variation): "
                f"{tc['amount_coefficient_of_variation']} -- supporting evidence only."
            )
        if tc["distinct_amounts_shared_across_customers"] > 0:
            evidence.append(
                f"{tc['distinct_amounts_shared_across_customers']} distinct transaction amount(s) "
                f"are each reused by more than one customer in this cluster."
            )

    ra = signals["return_anomaly"]
    if ra["insufficient_data"]:
        evidence.append(
            f"Only {ra['num_orders']} order(s) in this cluster -- too few to compute a "
            f"meaningful return rate."
        )
    else:
        evidence.append(
            f"Return rate: {ra['return_rate'] * 100:.1f}% across {ra['num_orders']} order(s) "
            f"(dataset baseline: {ra['baseline_return_rate'] * 100:.1f}%)."
        )
        if (
            ra["deviation_ratio"] is not None
            and ra["deviation_ratio"] >= config.evidence_return_rate_multiple_threshold
        ):
            evidence.append(
                f"Return rate is {ra['deviation_ratio']}x the dataset-wide baseline."
            )
        if ra["top_customer_return_share"] is not None and ra["top_customer_return_share"] >= 0.5:
            evidence.append(
                f"{ra['top_customer_return_share'] * 100:.0f}% of this cluster's returns come "
                f"from a single customer."
            )

    gc = signals["graph_connectivity"]
    evidence.append(
        f"Cluster graph: {gc['num_customer_nodes']} customer(s), {gc['num_device_nodes']} device(s), "
        f"{gc['num_network_nodes']} network(s), density {gc['density']}."
    )

    if not evidence:
        evidence.append("No notable signals beyond shared infrastructure membership.")

    return evidence


def build_cluster_evidence(
    cluster_id: str,
    customer_ids: list[str],
    device_ids: list[str],
    network_ids: list[str],
    transaction_ids: list[str],
    signals: dict,
    config: IntelligenceConfig,
) -> dict:
    """Assemble the final structured evidence dict for one candidate cluster.

    Deliberately excludes anything belonging to a later milestone: no
    risk score, no AI-investigator output, no confidence value, no
    recommended action. See the M2 architectural boundary in
    `pipeline.py`.
    """
    return {
        "cluster_id": cluster_id,
        "customers": customer_ids,
        "devices": device_ids,
        "networks": network_ids,
        "transactions": transaction_ids,
        "signals": signals,
        "evidence": build_evidence_strings(signals, config),
    }
