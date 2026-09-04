"""The seven frozen signal families.

Every function here returns a dict of INTERPRETABLE MEASUREMENTS, never
a verdict. None of these functions decide "abuse" or "not abuse" --
that judgement (informed by combinations of these signals, not any one
of them) belongs to a later milestone. See the module docstring in
`pipeline.py` for the full architectural boundary.

Design rule enforced throughout: shared device, shared IP, new
accounts, high return rate, and similar transaction amounts are each,
individually, explicitly NOT sufficient evidence of abuse -- so no
function below returns a boolean "is_suspicious" flag. They return
measurements; `features.py` turns measurements into human-readable
(but still non-judgemental) evidence strings.
"""

from __future__ import annotations

from datetime import timedelta

import networkx as nx
import numpy as np
import pandas as pd

from app.intelligence.baselines import GlobalBaselines
from app.intelligence.clustering import Cluster
from app.intelligence.config import IntelligenceConfig
from app.intelligence.data_loader import RawData
from app.intelligence.graph_builder import CUSTOMER, DEVICE, NETWORK


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------
def _cluster_customers(cluster: Cluster, data: RawData) -> pd.DataFrame:
    return data.customers[data.customers["id"].isin(cluster.customer_ids)]


def _cluster_device_links(cluster: Cluster, data: RawData) -> pd.DataFrame:
    return data.device_links[data.device_links["customer_id"].isin(cluster.customer_ids)]


def _cluster_network_links(cluster: Cluster, data: RawData) -> pd.DataFrame:
    return data.network_links[data.network_links["customer_id"].isin(cluster.customer_ids)]


def _cluster_transactions(cluster: Cluster, data: RawData) -> pd.DataFrame:
    tx = data.transactions[data.transactions["customer_id"].isin(cluster.customer_ids)]
    return tx.sort_values("created_at")


def _cluster_orders(cluster_tx: pd.DataFrame, data: RawData) -> pd.DataFrame:
    if cluster_tx.empty:
        return data.orders.iloc[0:0]
    return data.orders[data.orders["transaction_id"].isin(cluster_tx["id"])]


def _cluster_returns(cluster_orders: pd.DataFrame, data: RawData) -> pd.DataFrame:
    if cluster_orders.empty:
        return data.returns.iloc[0:0]
    return data.returns[data.returns["order_id"].isin(cluster_orders["id"])]


def _max_count_in_sliding_window(
    sorted_timestamps: list[pd.Timestamp], window: timedelta
) -> int:
    """Largest number of timestamps falling within any window of the given size.

    Two-pointer sweep over already-sorted timestamps -- O(n), not the
    O(n^2) naive "check every pair" approach.
    """
    n = len(sorted_timestamps)
    if n == 0:
        return 0
    left = 0
    best = 1
    for right in range(n):
        while sorted_timestamps[right] - sorted_timestamps[left] > window:
            left += 1
        best = max(best, right - left + 1)
    return best


# ----------------------------------------------------------------------
# Signal 1: SHARED DEVICE
# ----------------------------------------------------------------------
def shared_device_signal(cluster: Cluster, data: RawData) -> dict:
    links = _cluster_device_links(cluster, data)
    num_customers = len(cluster.customer_ids)

    if links.empty:
        return {
            "num_devices": 0,
            "device_customer_counts_in_cluster": {},
            "device_customer_counts_dataset_wide": {},
            "max_customers_per_device": 0,
            "shared_device_ratio": 0.0,
        }

    in_cluster_counts = links.groupby("device_id")["customer_id"].nunique()

    # Dataset-wide count per device: distinguishes "this device is only
    # ever used by cluster members" from "this device is a shared
    # kiosk/public terminal used by many unrelated customers too" --
    # useful context, not a verdict.
    dataset_wide_counts = (
        data.device_links[data.device_links["device_id"].isin(cluster.device_ids)]
        .groupby("device_id")["customer_id"]
        .nunique()
    )

    customers_on_shared_devices = links[
        links["device_id"].isin(in_cluster_counts[in_cluster_counts > 1].index)
    ]["customer_id"].nunique()

    return {
        "num_devices": len(cluster.device_ids),
        "device_customer_counts_in_cluster": in_cluster_counts.to_dict(),
        "device_customer_counts_dataset_wide": dataset_wide_counts.to_dict(),
        "max_customers_per_device": int(in_cluster_counts.max()),
        "shared_device_ratio": round(customers_on_shared_devices / num_customers, 4)
        if num_customers
        else 0.0,
    }


# ----------------------------------------------------------------------
# Signal 2: SHARED NETWORK / IP
# ----------------------------------------------------------------------
def shared_network_signal(cluster: Cluster, data: RawData) -> dict:
    links = _cluster_network_links(cluster, data)
    num_customers = len(cluster.customer_ids)

    if links.empty:
        return {
            "num_networks": 0,
            "network_customer_counts_in_cluster": {},
            "network_customer_counts_dataset_wide": {},
            "max_customers_per_network": 0,
            "shared_network_ratio": 0.0,
        }

    in_cluster_counts = links.groupby("network_id")["customer_id"].nunique()

    dataset_wide_counts = (
        data.network_links[data.network_links["network_id"].isin(cluster.network_ids)]
        .groupby("network_id")["customer_id"]
        .nunique()
    )

    customers_on_shared_networks = links[
        links["network_id"].isin(in_cluster_counts[in_cluster_counts > 1].index)
    ]["customer_id"].nunique()

    return {
        "num_networks": len(cluster.network_ids),
        "network_customer_counts_in_cluster": in_cluster_counts.to_dict(),
        "network_customer_counts_dataset_wide": dataset_wide_counts.to_dict(),
        "max_customers_per_network": int(in_cluster_counts.max()),
        "shared_network_ratio": round(customers_on_shared_networks / num_customers, 4)
        if num_customers
        else 0.0,
    }


# ----------------------------------------------------------------------
# Signal 3: ACCOUNT CREATION BURST
# ----------------------------------------------------------------------
def account_creation_burst_signal(
    cluster: Cluster, data: RawData, config: IntelligenceConfig
) -> dict:
    customers = _cluster_customers(cluster, data)
    n = len(customers)

    if n == 0:
        return {
            "num_customers": 0,
            "creation_time_span_hours": 0.0,
            "max_accounts_in_window": 0,
            "window_hours": config.creation_burst_window_hours,
            "burst_ratio": 0.0,
        }

    times = sorted(customers["created_at"].tolist())
    span_hours = (times[-1] - times[0]).total_seconds() / 3600 if n > 1 else 0.0
    window = timedelta(hours=config.creation_burst_window_hours)
    max_in_window = _max_count_in_sliding_window(times, window)

    return {
        "num_customers": n,
        "creation_time_span_hours": round(span_hours, 2),
        "max_accounts_in_window": max_in_window,
        "window_hours": config.creation_burst_window_hours,
        "burst_ratio": round(max_in_window / n, 4),
    }


# ----------------------------------------------------------------------
# Signal 4: TRANSACTION VELOCITY
# ----------------------------------------------------------------------
def transaction_velocity_signal(
    cluster: Cluster,
    data: RawData,
    config: IntelligenceConfig,
    baselines: GlobalBaselines,
) -> dict:
    tx = _cluster_transactions(cluster, data)
    n = len(tx)
    num_customers = len(cluster.customer_ids)

    if n == 0:
        return {
            "num_transactions": 0,
            "transactions_per_customer": 0.0,
            "max_transactions_in_window": 0,
            "window_hours": config.velocity_window_hours,
            "activity_span_hours": 0.0,
            "baseline_transactions_per_customer": round(
                baselines.avg_transactions_per_customer, 4
            ),
            "velocity_ratio_vs_baseline": None,
        }

    times = sorted(tx["created_at"].tolist())
    span_hours = (times[-1] - times[0]).total_seconds() / 3600 if n > 1 else 0.0
    window = timedelta(hours=config.velocity_window_hours)
    max_in_window = _max_count_in_sliding_window(times, window)

    tx_per_customer = n / num_customers if num_customers else 0.0
    baseline = baselines.avg_transactions_per_customer
    velocity_ratio = (tx_per_customer / baseline) if baseline > 0 else None

    return {
        "num_transactions": n,
        "transactions_per_customer": round(tx_per_customer, 4),
        "max_transactions_in_window": max_in_window,
        "window_hours": config.velocity_window_hours,
        "activity_span_hours": round(span_hours, 2),
        "baseline_transactions_per_customer": round(baseline, 4),
        "velocity_ratio_vs_baseline": round(velocity_ratio, 4) if velocity_ratio is not None else None,
    }


# ----------------------------------------------------------------------
# Signal 5: TRANSACTION COORDINATION
# ----------------------------------------------------------------------
def transaction_coordination_signal(
    cluster: Cluster, data: RawData, config: IntelligenceConfig
) -> dict:
    tx = _cluster_transactions(cluster, data)
    n = len(tx)

    if n < 2:
        return {
            "num_transactions": n,
            "temporal_coordination_ratio": 0.0,
            "proximity_window_minutes": config.coordination_proximity_minutes,
            "amount_coefficient_of_variation": None,
            "distinct_amounts_shared_across_customers": 0,
        }

    times = tx["created_at"].tolist()
    customers = tx["customer_id"].tolist()
    window = timedelta(minutes=config.coordination_proximity_minutes)

    # For each transaction, is there at least one OTHER customer's
    # transaction within the proximity window (looking BOTH backward
    # and forward in time, not just at what came before it)? This is
    # deliberately independent of amount -- a cluster with wildly
    # different amounts (Rs 15,000 / Rs 500 / Rs 8,700) can still score
    # high here if the timing lines up, per the spec's explicit example.
    #
    # Two monotonic pointers (lo, hi) sweep forward together with the
    # loop index -- O(n) total, not O(n^2), and symmetric: transaction
    # 0 in a tight cluster gets credit for transaction 1 following it,
    # not just for transactions that preceded it.
    coordinated_count = 0
    lo = 0
    hi = 0
    for i in range(n):
        if lo < i:
            while times[i] - times[lo] > window:
                lo += 1
        if hi < i:
            hi = i
        while hi + 1 < n and times[hi + 1] - times[i] <= window:
            hi += 1

        has_other_customer = any(
            customers[j] != customers[i] for j in range(lo, hi + 1) if j != i
        )
        if has_other_customer:
            coordinated_count += 1
    temporal_coordination_ratio = coordinated_count / n

    # Amount similarity -- SUPPORTING evidence only, never required.
    amounts = tx["amount"].to_numpy(dtype=float)
    mean_amount = float(amounts.mean())
    cv = float(amounts.std() / mean_amount) if mean_amount > 0 else None

    # Repeated-pattern evidence: approximately similar amounts reused across
    # more than one distinct customer. This uses the configured tolerance
    # instead of exact equality, so a coordinated ring can still be surfaced
    # when gateway/order rounding or small amount variation is present.
    # Supporting evidence only -- it never becomes a standalone verdict.
    amounts_sorted = tx[["amount", "customer_id"]].sort_values("amount")
    amount_values = amounts_sorted["amount"].to_numpy(dtype=float)
    amount_customers = amounts_sorted["customer_id"].to_numpy()
    tolerance = config.amount_similarity_tolerance
    repeated_amount_count = 0
    seen_amount_bands: set[tuple[str, str]] = set()
    for i in range(len(amount_values)):
        amount = amount_values[i]
        if amount <= 0:
            continue
        # |a-b| / max(a,b) <= tolerance, rearranged for b >= a.
        upper = amount / (1.0 - tolerance) if tolerance < 1.0 else float("inf")
        j = i + 1
        customers_in_band = {str(amount_customers[i])}
        while j < len(amount_values) and amount_values[j] <= upper:
            customers_in_band.add(str(amount_customers[j]))
            j += 1
        if len(customers_in_band) > 1:
            # Count distinct bands, not every transaction pair, keeping the
            # measurement stable when a cluster has many repeated payments.
            band_key = (f"{amount:.2f}", ",".join(sorted(customers_in_band)))
            if band_key not in seen_amount_bands:
                seen_amount_bands.add(band_key)
                repeated_amount_count += 1

    return {
        "num_transactions": n,
        "temporal_coordination_ratio": round(temporal_coordination_ratio, 4),
        "proximity_window_minutes": config.coordination_proximity_minutes,
        "amount_coefficient_of_variation": round(cv, 4) if cv is not None else None,
        "distinct_amounts_shared_across_customers": repeated_amount_count,
    }


# ----------------------------------------------------------------------
# Signal 6: RETURN ANOMALY
# ----------------------------------------------------------------------
def return_anomaly_signal(
    cluster: Cluster,
    data: RawData,
    config: IntelligenceConfig,
    baselines: GlobalBaselines,
) -> dict:
    tx = _cluster_transactions(cluster, data)
    orders = _cluster_orders(tx, data)
    returns = _cluster_returns(orders, data)

    num_orders = len(orders)
    num_returns = len(returns)

    if num_orders < config.min_orders_for_return_rate:
        return {
            "num_orders": num_orders,
            "num_returns": num_returns,
            "return_rate": None,
            "baseline_return_rate": round(baselines.global_return_rate, 4),
            "deviation_ratio": None,
            "top_customer_return_share": None,
            "insufficient_data": True,
        }

    return_rate = num_returns / num_orders
    deviation_ratio = (
        (return_rate / baselines.global_return_rate)
        if baselines.global_return_rate > 0
        else None
    )

    top_customer_share = None
    if num_returns > 0:
        # Trace each return back to the customer who made it, to see
        # whether returns are spread across the cluster or concentrated
        # in one or two accounts.
        returns_with_tx = returns.merge(
            orders[["id", "transaction_id"]], left_on="order_id", right_on="id", suffixes=("", "_order")
        )
        returns_with_customer = returns_with_tx.merge(
            tx[["id", "customer_id"]], left_on="transaction_id", right_on="id", suffixes=("", "_tx")
        )
        if not returns_with_customer.empty:
            top_count = returns_with_customer["customer_id"].value_counts().iloc[0]
            top_customer_share = round(float(top_count / num_returns), 4)

    return {
        "num_orders": num_orders,
        "num_returns": num_returns,
        "return_rate": round(return_rate, 4),
        "baseline_return_rate": round(baselines.global_return_rate, 4),
        "deviation_ratio": round(deviation_ratio, 4) if deviation_ratio is not None else None,
        "top_customer_return_share": top_customer_share,
        "insufficient_data": False,
    }


# ----------------------------------------------------------------------
# Signal 7: GRAPH CONNECTIVITY / STRUCTURE
# ----------------------------------------------------------------------
# Above this many nodes, skip diameter (all-pairs shortest paths is
# expensive) -- density/degree stats remain cheap at any size.
_DIAMETER_NODE_LIMIT = 300


def graph_connectivity_signal(cluster: Cluster, relationship_graph: nx.Graph) -> dict:
    node_ids = (
        [f"{CUSTOMER}:{cid}" for cid in cluster.customer_ids]
        + [f"{DEVICE}:{did}" for did in cluster.device_ids]
        + [f"{NETWORK}:{nid}" for nid in cluster.network_ids]
    )
    subgraph = relationship_graph.subgraph(node_ids)

    num_customer_nodes = len(cluster.customer_ids)
    num_device_nodes = len(cluster.device_ids)
    num_network_nodes = len(cluster.network_ids)
    num_edges = subgraph.number_of_edges()
    total_nodes = subgraph.number_of_nodes()

    density = nx.density(subgraph) if total_nodes > 1 else 0.0

    customer_nodes = [n for n in subgraph.nodes if subgraph.nodes[n]["type"] == CUSTOMER]
    avg_customer_degree = (
        sum(dict(subgraph.degree(customer_nodes)).values()) / len(customer_nodes)
        if customer_nodes
        else 0.0
    )

    is_connected = nx.is_connected(subgraph) if total_nodes > 0 else False

    diameter = None
    if is_connected and total_nodes <= _DIAMETER_NODE_LIMIT:
        try:
            diameter = nx.diameter(subgraph)
        except nx.NetworkXError:
            diameter = None

    return {
        "num_customer_nodes": num_customer_nodes,
        "num_device_nodes": num_device_nodes,
        "num_network_nodes": num_network_nodes,
        "num_edges": num_edges,
        "density": round(density, 4),
        "avg_customer_degree": round(avg_customer_degree, 4),
        "is_connected": is_connected,
        "diameter": diameter,
    }
