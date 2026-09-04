"""Observable feature extraction for TrustGraph's ML secondary signal."""

from __future__ import annotations

import math
from typing import Any

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


def _safe_float(value: Any) -> float:
    if value is None:
        return float("nan")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return value if math.isfinite(value) else float("nan")


def cluster_to_features(cluster: Any) -> list[float]:
    """Build the exact 30-feature vector used by the validated GBM experiment.

    Intentionally excluded: ground truth, deterministic risk score/risk level,
    Gemini output, policy decision, and any future-stage information.
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
        _safe_float(len(cluster.customers)),
        _safe_float(sd.get("num_devices")),
        _safe_float(sd.get("max_customers_per_device")),
        _safe_float(sd.get("shared_device_ratio")),
        _safe_float(sn.get("num_networks")),
        _safe_float(sn.get("max_customers_per_network")),
        _safe_float(sn.get("shared_network_ratio")),
        _safe_float(cb.get("creation_time_span_hours")),
        _safe_float(cb.get("max_accounts_in_window")),
        _safe_float(cb.get("burst_ratio")),
        _safe_float(tv.get("num_transactions")),
        _safe_float(tv.get("transactions_per_customer")),
        _safe_float(tv.get("max_transactions_in_window")),
        _safe_float(tv.get("activity_span_hours")),
        _safe_float(tv.get("velocity_ratio_vs_baseline")),
        _safe_float(tc.get("temporal_coordination_ratio")),
        _safe_float(tc.get("amount_coefficient_of_variation")),
        _safe_float(tc.get("distinct_amounts_shared_across_customers")),
        _safe_float(ra.get("num_orders")),
        _safe_float(ra.get("num_returns")),
        _safe_float(ra.get("return_rate")),
        _safe_float(ra.get("deviation_ratio")),
        _safe_float(ra.get("top_customer_return_share")),
        _safe_float(gc.get("num_customer_nodes")),
        _safe_float(gc.get("num_device_nodes")),
        _safe_float(gc.get("num_network_nodes")),
        _safe_float(gc.get("num_edges")),
        _safe_float(gc.get("density")),
        _safe_float(gc.get("avg_customer_degree")),
        _safe_float(gc.get("diameter")),
    ]
