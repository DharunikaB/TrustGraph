"""Tests for the M2 intelligence engine.

Two testing styles are used:

- Direct `RawData` construction (`_raw_data(...)`) for signal-level
  tests that need exact control over timestamps/amounts to assert
  precise expected numbers (e.g. "exactly 3 accounts fall inside this
  48h window").
- DB-backed scenarios (via the SQLite `async_session` fixture from
  `conftest.py`) for graph construction / loader integration tests,
  so the ORM -> DataFrame -> graph path is exercised end-to-end too.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.intelligence.clustering import Cluster, find_candidate_clusters
from app.intelligence.config import IntelligenceConfig
from app.intelligence.data_loader import RawData, load_raw_data
from app.intelligence.graph_builder import (
    build_full_graph,
    build_relationship_graph,
    customer_ids_in_component,
)
from app.intelligence.pipeline import run_pipeline
from app.intelligence.signals import (
    account_creation_burst_signal,
    graph_connectivity_signal,
    return_anomaly_signal,
    shared_device_signal,
    shared_network_signal,
    transaction_coordination_signal,
    transaction_velocity_signal,
)
from app.intelligence.baselines import compute_global_baselines
from app.models import (
    Customer,
    CustomerDeviceLink,
    CustomerNetworkLink,
    Device,
    Merchant,
    NetworkIdentifier,
    Order,
    Return,
    Transaction,
    TransactionStatus,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# Direct RawData construction helpers
# ----------------------------------------------------------------------
def _df(records: list[dict], columns: list[str]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(records)[columns]


def _raw_data(
    customers: list[dict],
    devices: list[dict] | None = None,
    networks: list[dict] | None = None,
    device_links: list[dict] | None = None,
    network_links: list[dict] | None = None,
    transactions: list[dict] | None = None,
    orders: list[dict] | None = None,
    returns: list[dict] | None = None,
) -> RawData:
    return RawData(
        customers=_df(customers, ["id", "merchant_id", "created_at"]),
        devices=_df(devices or [], ["id", "device_fingerprint", "created_at"]),
        networks=_df(networks or [], ["id", "ip_address", "created_at"]),
        device_links=_df(device_links or [], ["customer_id", "device_id", "first_seen", "last_seen"]),
        network_links=_df(network_links or [], ["customer_id", "network_id", "first_seen", "last_seen"]),
        transactions=_df(
            transactions or [],
            ["id", "customer_id", "device_id", "network_id", "amount", "currency", "status", "created_at"],
        ),
        orders=_df(orders or [], ["id", "transaction_id", "order_amount", "created_at"]),
        returns=_df(returns or [], ["id", "order_id", "amount", "reason", "created_at"]),
    )


def _legitimate_shared_infra_scenario() -> tuple[RawData, list[str]]:
    """4 customers genuinely sharing one device and one IP (e.g. a family).

    Account creation spread over months, transactions independently
    timed with varied amounts, ordinary return rate. Nothing here
    should read as coordinated.
    """
    customer_ids = [f"legit-c{i}" for i in range(4)]
    device_id, network_id = "legit-device", "legit-network"

    customers = [
        {"id": cid, "merchant_id": "m1", "created_at": T0 + timedelta(days=30 * i)}
        for i, cid in enumerate(customer_ids)
    ]
    devices = [{"id": device_id, "device_fingerprint": "fp-legit", "created_at": T0}]
    networks = [{"id": network_id, "ip_address": "10.0.0.1", "created_at": T0}]
    device_links = [
        {"customer_id": cid, "device_id": device_id, "first_seen": c["created_at"], "last_seen": c["created_at"]}
        for cid, c in zip(customer_ids, customers)
    ]
    network_links = [
        {"customer_id": cid, "network_id": network_id, "first_seen": c["created_at"], "last_seen": c["created_at"]}
        for cid, c in zip(customer_ids, customers)
    ]

    transactions = []
    orders = []
    returns = []
    amounts = [120.0, 4800.0, 950.0, 60.0]  # deliberately varied, independent
    for i, (cid, cust) in enumerate(zip(customer_ids, customers)):
        for j in range(2):
            tx_id = f"legit-tx-{i}-{j}"
            tx_time = cust["created_at"] + timedelta(days=10 * j + i)  # spread out, not coordinated
            transactions.append(
                {
                    "id": tx_id,
                    "customer_id": cid,
                    "device_id": device_id,
                    "network_id": network_id,
                    "amount": amounts[i] + j * 5,
                    "currency": "INR",
                    "status": "success",
                    "created_at": tx_time,
                }
            )
            order_id = f"legit-order-{i}-{j}"
            orders.append(
                {
                    "id": order_id,
                    "transaction_id": tx_id,
                    "order_amount": amounts[i] + j * 5,
                    "created_at": tx_time + timedelta(minutes=5),
                }
            )
    # exactly one ordinary return, out of 8 orders (12.5%)
    returns.append(
        {
            "id": "legit-return-0",
            "order_id": "legit-order-0-0",
            "amount": amounts[0],
            "reason": "changed_mind",
            "created_at": T0 + timedelta(days=15),
        }
    )

    data = _raw_data(customers, devices, networks, device_links, network_links, transactions, orders, returns)
    return data, customer_ids


def _suspicious_coordinated_scenario() -> tuple[RawData, list[str]]:
    """4 customers sharing one device and one IP, created within hours of
    each other, transacting within minutes of each other, high returns.
    """
    customer_ids = [f"sus-c{i}" for i in range(4)]
    device_id, network_id = "sus-device", "sus-network"

    burst_start = T0
    customers = [
        {"id": cid, "merchant_id": "m1", "created_at": burst_start + timedelta(minutes=20 * i)}
        for i, cid in enumerate(customer_ids)
    ]
    devices = [{"id": device_id, "device_fingerprint": "fp-sus", "created_at": T0}]
    networks = [{"id": network_id, "ip_address": "10.0.0.2", "created_at": T0}]
    device_links = [
        {"customer_id": cid, "device_id": device_id, "first_seen": c["created_at"], "last_seen": c["created_at"]}
        for cid, c in zip(customer_ids, customers)
    ]
    network_links = [
        {"customer_id": cid, "network_id": network_id, "first_seen": c["created_at"], "last_seen": c["created_at"]}
        for cid, c in zip(customer_ids, customers)
    ]

    tx_start = burst_start + timedelta(hours=1)
    transactions = []
    orders = []
    returns = []
    # Deliberately DIFFERENT amounts (per spec's explicit example) --
    # coordination must be detectable from timing alone.
    amounts = [15000.0, 500.0, 8700.0, 3200.0]
    for i, cid in enumerate(customer_ids):
        tx_id = f"sus-tx-{i}"
        tx_time = tx_start + timedelta(minutes=5 * i)  # all within ~15 minutes
        transactions.append(
            {
                "id": tx_id,
                "customer_id": cid,
                "device_id": device_id,
                "network_id": network_id,
                "amount": amounts[i],
                "currency": "INR",
                "status": "success",
                "created_at": tx_time,
            }
        )
        order_id = f"sus-order-{i}"
        orders.append(
            {
                "id": order_id,
                "transaction_id": tx_id,
                "order_amount": amounts[i],
                "created_at": tx_time + timedelta(minutes=2),
            }
        )
        # 3 of 4 orders returned -- high return rate
        if i < 3:
            returns.append(
                {
                    "id": f"sus-return-{i}",
                    "order_id": order_id,
                    "amount": amounts[i],
                    "reason": "duplicate_order",
                    "created_at": tx_time + timedelta(days=1),
                }
            )

    data = _raw_data(customers, devices, networks, device_links, network_links, transactions, orders, returns)
    return data, customer_ids


# ----------------------------------------------------------------------
# 1-4: Graph construction, relationships, connected components
# ----------------------------------------------------------------------
def test_relationship_graph_connects_customers_via_shared_device():
    data, customer_ids = _legitimate_shared_infra_scenario()
    graph = build_relationship_graph(data)

    components = list(nx_connected_components(graph))
    assert len(components) == 1
    found = customer_ids_in_component(graph, components[0])
    assert found == sorted(customer_ids)


def test_relationship_graph_keeps_isolated_customers_separate():
    customers = [
        {"id": "iso-1", "merchant_id": "m1", "created_at": T0},
        {"id": "iso-2", "merchant_id": "m1", "created_at": T0},
    ]
    devices = [
        {"id": "d1", "device_fingerprint": "fp1", "created_at": T0},
        {"id": "d2", "device_fingerprint": "fp2", "created_at": T0},
    ]
    device_links = [
        {"customer_id": "iso-1", "device_id": "d1", "first_seen": T0, "last_seen": T0},
        {"customer_id": "iso-2", "device_id": "d2", "first_seen": T0, "last_seen": T0},
    ]
    data = _raw_data(customers, devices, device_links=device_links)
    graph = build_relationship_graph(data)

    components = list(nx_connected_components(graph))
    assert len(components) == 2  # not merged -- different devices


def test_customer_device_and_network_edges_have_correct_type():
    data, _ = _legitimate_shared_infra_scenario()
    graph = build_relationship_graph(data)
    edge_types = {data["type"] for _, _, data in graph.edges(data=True)}
    assert edge_types == {"USES_DEVICE", "CONNECTED_FROM"}


def test_full_graph_includes_transaction_order_return_chain():
    data, _ = _legitimate_shared_infra_scenario()
    graph = build_full_graph(data)
    edge_types = {edata["type"] for _, _, edata in graph.edges(data=True)}
    assert "MADE_TRANSACTION" in edge_types
    assert "HAS_ORDER" in edge_types
    assert "RESULTED_IN_RETURN" in edge_types


def test_candidate_clusters_exclude_isolated_customers():
    data, _ = _legitimate_shared_infra_scenario()
    # Add an isolated customer with no shared device/network.
    isolated = pd.DataFrame(
        [{"id": "solo-1", "merchant_id": "m1", "created_at": T0}]
    )
    data.customers = pd.concat([data.customers, isolated], ignore_index=True)

    config = IntelligenceConfig()
    graph = build_relationship_graph(data)
    clusters = find_candidate_clusters(graph, config)

    all_clustered_customers = {cid for c in clusters for cid in c.customer_ids}
    assert "solo-1" not in all_clustered_customers
    assert len(clusters) == 1
    assert len(clusters[0].customer_ids) == 4


def nx_connected_components(graph):
    import networkx as nx

    return nx.connected_components(graph)


# ----------------------------------------------------------------------
# 5-6: Shared device / shared network signals
# ----------------------------------------------------------------------
def test_shared_device_signal_measures_without_judging():
    data, customer_ids = _legitimate_shared_infra_scenario()
    cluster = Cluster("cc-0", sorted(customer_ids), ["legit-device"], ["legit-network"])

    result = shared_device_signal(cluster, data)
    assert result["num_devices"] == 1
    assert result["max_customers_per_device"] == 4
    assert result["shared_device_ratio"] == 1.0
    # Must be pure measurement -- no verdict key of any kind.
    assert "is_abuse" not in result
    assert "risk" not in result
    assert "suspicious" not in result


def test_shared_network_signal_measures_without_judging():
    data, customer_ids = _legitimate_shared_infra_scenario()
    cluster = Cluster("cc-0", sorted(customer_ids), ["legit-device"], ["legit-network"])

    result = shared_network_signal(cluster, data)
    assert result["num_networks"] == 1
    assert result["max_customers_per_network"] == 4
    assert result["shared_network_ratio"] == 1.0


def test_shared_device_signal_with_no_devices_is_safe():
    data = _raw_data([{"id": "c1", "merchant_id": "m1", "created_at": T0}])
    cluster = Cluster("cc-0", ["c1"], [], [])
    result = shared_device_signal(cluster, data)
    assert result["num_devices"] == 0
    assert result["shared_device_ratio"] == 0.0


# ----------------------------------------------------------------------
# 7: Account creation burst
# ----------------------------------------------------------------------
def test_account_creation_burst_detects_concentrated_window():
    customers = [
        {"id": "b1", "merchant_id": "m1", "created_at": T0},
        {"id": "b2", "merchant_id": "m1", "created_at": T0 + timedelta(hours=1)},
        {"id": "b3", "merchant_id": "m1", "created_at": T0 + timedelta(hours=2)},
        # This one is far outside the burst window.
        {"id": "b4", "merchant_id": "m1", "created_at": T0 + timedelta(days=30)},
    ]
    data = _raw_data(customers)
    cluster = Cluster("cc-0", ["b1", "b2", "b3", "b4"], [], [])
    config = IntelligenceConfig(creation_burst_window_hours=48)

    result = account_creation_burst_signal(cluster, data, config)
    assert result["num_customers"] == 4
    assert result["max_accounts_in_window"] == 3  # b1, b2, b3 fall in one 48h window
    assert result["burst_ratio"] == pytest.approx(0.75)


def test_account_creation_burst_spread_out_gives_low_ratio():
    customers = [
        {"id": f"s{i}", "merchant_id": "m1", "created_at": T0 + timedelta(days=60 * i)}
        for i in range(4)
    ]
    data = _raw_data(customers)
    cluster = Cluster("cc-0", [c["id"] for c in customers], [], [])
    config = IntelligenceConfig(creation_burst_window_hours=48)

    result = account_creation_burst_signal(cluster, data, config)
    assert result["max_accounts_in_window"] == 1
    assert result["burst_ratio"] == pytest.approx(0.25)


# ----------------------------------------------------------------------
# 8: Transaction velocity
# ----------------------------------------------------------------------
def test_transaction_velocity_ratio_vs_baseline():
    data, customer_ids = _suspicious_coordinated_scenario()
    cluster = Cluster("cc-0", sorted(customer_ids), ["sus-device"], ["sus-network"])
    baselines = compute_global_baselines(data)
    config = IntelligenceConfig()

    result = transaction_velocity_signal(cluster, data, config, baselines)
    assert result["num_transactions"] == 4
    # 4 transactions / 4 customers == 1.0 per customer, equal to the
    # (self-same, in this isolated scenario) baseline.
    assert result["transactions_per_customer"] == pytest.approx(1.0)
    assert result["velocity_ratio_vs_baseline"] == pytest.approx(1.0)


def test_transaction_velocity_handles_zero_transactions():
    data = _raw_data([{"id": "c1", "merchant_id": "m1", "created_at": T0}])
    cluster = Cluster("cc-0", ["c1"], [], [])
    baselines = compute_global_baselines(data)
    result = transaction_velocity_signal(cluster, data, IntelligenceConfig(), baselines)
    assert result["num_transactions"] == 0
    assert result["velocity_ratio_vs_baseline"] is None


# ----------------------------------------------------------------------
# 9: Transaction coordination (amount similarity must NOT be required)
# ----------------------------------------------------------------------
def test_coordination_detected_despite_very_different_amounts():
    """Per spec: 15000 / 500 / 8700 should still register as coordinated
    if the timing lines up -- amount similarity is supporting only."""
    data, customer_ids = _suspicious_coordinated_scenario()
    cluster = Cluster("cc-0", sorted(customer_ids), ["sus-device"], ["sus-network"])
    config = IntelligenceConfig(coordination_proximity_minutes=60)

    result = transaction_coordination_signal(cluster, data, config)
    # All 4 transactions fall within a 15-minute span -- every one of
    # them has at least one other customer's transaction within the
    # 60-minute proximity window.
    assert result["temporal_coordination_ratio"] == pytest.approx(1.0)
    # Amounts are wildly different -- coordination was NOT amount-driven.
    assert result["amount_coefficient_of_variation"] > 0.5


def test_coordination_low_for_independently_timed_transactions():
    data, customer_ids = _legitimate_shared_infra_scenario()
    cluster = Cluster("cc-0", sorted(customer_ids), ["legit-device"], ["legit-network"])
    config = IntelligenceConfig(coordination_proximity_minutes=60)

    result = transaction_coordination_signal(cluster, data, config)
    assert result["temporal_coordination_ratio"] == 0.0


def test_coordination_handles_single_transaction():
    data = _raw_data(
        [{"id": "c1", "merchant_id": "m1", "created_at": T0}],
        transactions=[
            {
                "id": "tx1",
                "customer_id": "c1",
                "device_id": None,
                "network_id": None,
                "amount": 100.0,
                "currency": "INR",
                "status": "success",
                "created_at": T0,
            }
        ],
    )
    cluster = Cluster("cc-0", ["c1"], [], [])
    result = transaction_coordination_signal(cluster, data, IntelligenceConfig())
    assert result["temporal_coordination_ratio"] == 0.0
    assert result["amount_coefficient_of_variation"] is None


# ----------------------------------------------------------------------
# 10: Return anomaly
# ----------------------------------------------------------------------
def test_return_anomaly_flags_insufficient_data_for_tiny_clusters():
    data, customer_ids = _legitimate_shared_infra_scenario()
    # Restrict to a fake cluster with almost no orders.
    tiny_cluster = Cluster("cc-0", ["legit-c0"], ["legit-device"], ["legit-network"])
    baselines = compute_global_baselines(data)
    config = IntelligenceConfig(min_orders_for_return_rate=5)

    result = return_anomaly_signal(tiny_cluster, data, config, baselines)
    assert result["insufficient_data"] is True
    assert result["return_rate"] is None


def test_return_anomaly_deviation_ratio_against_baseline():
    data, customer_ids = _suspicious_coordinated_scenario()
    cluster = Cluster("cc-0", sorted(customer_ids), ["sus-device"], ["sus-network"])
    baselines = compute_global_baselines(data)
    config = IntelligenceConfig(min_orders_for_return_rate=2)

    result = return_anomaly_signal(cluster, data, config, baselines)
    assert result["num_orders"] == 4
    assert result["num_returns"] == 3
    assert result["return_rate"] == pytest.approx(0.75)
    # In this isolated scenario the cluster IS the whole dataset, so
    # deviation ratio should be ~1 (cluster rate == baseline rate).
    assert result["deviation_ratio"] == pytest.approx(1.0)


def test_return_anomaly_handles_zero_returns():
    data, customer_ids = _legitimate_shared_infra_scenario()
    # Drop the one seeded return so this cluster has zero.
    data.returns = data.returns.iloc[0:0]
    cluster = Cluster("cc-0", sorted(customer_ids), ["legit-device"], ["legit-network"])
    baselines = compute_global_baselines(data)
    config = IntelligenceConfig(min_orders_for_return_rate=2)

    result = return_anomaly_signal(cluster, data, config, baselines)
    assert result["num_returns"] == 0
    assert result["return_rate"] == 0.0
    assert result["top_customer_return_share"] is None  # no division by zero


# ----------------------------------------------------------------------
# 11: Graph connectivity metrics
# ----------------------------------------------------------------------
def test_graph_connectivity_metrics_on_known_star_shape():
    data, customer_ids = _legitimate_shared_infra_scenario()
    graph = build_relationship_graph(data)
    cluster = Cluster("cc-0", sorted(customer_ids), ["legit-device"], ["legit-network"])

    result = graph_connectivity_signal(cluster, graph)
    assert result["num_customer_nodes"] == 4
    assert result["num_device_nodes"] == 1
    assert result["num_network_nodes"] == 1
    # Each of 4 customers connects to 1 device + 1 network = 8 edges.
    assert result["num_edges"] == 8
    assert result["is_connected"] is True
    assert result["avg_customer_degree"] == pytest.approx(2.0)


# ----------------------------------------------------------------------
# 12-13: Full pipeline -- legitimate vs suspicious
# ----------------------------------------------------------------------
def test_legitimate_shared_infrastructure_is_not_labelled_abuse():
    data, customer_ids = _legitimate_shared_infra_scenario()
    results = run_pipeline(data)

    assert len(results) == 1
    cluster = results[0]
    assert sorted(cluster["customers"]) == sorted(customer_ids)

    # The pipeline must never emit a verdict of any kind.
    forbidden_keys = {"is_abuse", "risk_score", "abuse_score", "confidence", "action", "label"}
    assert forbidden_keys.isdisjoint(cluster.keys())
    assert forbidden_keys.isdisjoint(cluster["signals"].keys())
    for signal_values in cluster["signals"].values():
        assert forbidden_keys.isdisjoint(signal_values.keys())

    # Shared-device/network evidence exists...
    assert cluster["signals"]["shared_device"]["shared_device_ratio"] == 1.0
    # ...but the behavioral signals should look unremarkable.
    assert cluster["signals"]["account_creation_burst"]["burst_ratio"] < 0.5
    assert cluster["signals"]["transaction_coordination"]["temporal_coordination_ratio"] == 0.0


def test_suspicious_coordinated_pattern_shows_elevated_signals():
    data, customer_ids = _suspicious_coordinated_scenario()
    results = run_pipeline(data)

    assert len(results) == 1
    cluster = results[0]

    # Still no verdict -- just much more pronounced measurements than
    # the legitimate scenario above.
    assert "is_abuse" not in cluster
    assert cluster["signals"]["account_creation_burst"]["burst_ratio"] == 1.0
    assert cluster["signals"]["transaction_coordination"]["temporal_coordination_ratio"] == 1.0
    assert cluster["signals"]["return_anomaly"]["return_rate"] == pytest.approx(0.75)


# ----------------------------------------------------------------------
# 14: Ground truth leakage prevention
# ----------------------------------------------------------------------
def test_intelligence_source_never_references_ground_truth():
    """Static check: no file under app/intelligence actually USES ground
    truth (imports the model, queries the table, or reads a ground-truth
    key). Documentation *mentioning* ground truth (e.g. this module's own
    "we must never do X" docstrings) is fine and expected -- only real
    usage patterns are forbidden here.
    """
    forbidden_patterns = [
        "import GroundTruth",
        "GroundTruth(",
        "GroundTruthLabel.",
        "GroundTruthLabel(",
        "select(GroundTruth",
        '"ground_truth"',
        "'ground_truth'",
        '["is_abuse"]',
        "['is_abuse']",
        ".is_abuse",
    ]
    intelligence_dir = Path(__file__).resolve().parents[1] / "app" / "intelligence"

    for py_file in intelligence_dir.glob("*.py"):
        content = py_file.read_text()
        for pattern in forbidden_patterns:
            assert pattern not in content, f"{py_file.name} references forbidden pattern {pattern!r}"


def test_raw_data_never_contains_ground_truth_columns():
    data, _ = _legitimate_shared_infra_scenario()
    forbidden_columns = {"is_abuse", "label", "cluster_id", "ground_truth"}
    for frame_name in ("customers", "transactions", "orders", "returns", "devices", "networks"):
        frame = getattr(data, frame_name)
        assert forbidden_columns.isdisjoint(frame.columns), f"{frame_name} leaks ground truth"


def test_pipeline_output_never_contains_ground_truth_keys():
    data, _ = _suspicious_coordinated_scenario()
    results = run_pipeline(data)
    output_json = json.dumps(results, default=str)
    for token in ("ground_truth", "is_abuse", "abuse_ring"):
        assert token not in output_json


@pytest.mark.asyncio
async def test_data_loader_does_not_query_ground_truth_table(async_session):
    """End-to-end: even with a GroundTruth row present in the DB, the
    loader used by the intelligence pipeline must not surface it."""
    from app.models import GroundTruth, GroundTruthLabel

    merchant = Merchant(name="M")
    async_session.add(merchant)
    await async_session.flush()

    customer = Customer(merchant_id=merchant.id, email="gt@example.com", display_name="GT")
    async_session.add(customer)
    await async_session.flush()

    async_session.add(
        GroundTruth(customer_id=customer.id, label=GroundTruthLabel.COORDINATED_ABUSE, is_abuse=True)
    )
    await async_session.commit()

    data = await load_raw_data(async_session)
    assert "label" not in data.customers.columns
    assert "is_abuse" not in data.customers.columns
    assert len(data.customers) == 1  # customer itself IS observable data


# ----------------------------------------------------------------------
# 15: Determinism
# ----------------------------------------------------------------------
def test_pipeline_is_deterministic():
    data, _ = _suspicious_coordinated_scenario()
    result_a = run_pipeline(data)
    result_b = run_pipeline(data)
    assert json.dumps(result_a, default=str) == json.dumps(result_b, default=str)


def test_cluster_ids_are_deterministic_regardless_of_customer_row_order():
    data, customer_ids = _legitimate_shared_infra_scenario()
    shuffled = data.customers.iloc[::-1].reset_index(drop=True)
    data_shuffled = _raw_data(
        shuffled.to_dict("records"),
        data.devices.to_dict("records"),
        data.networks.to_dict("records"),
        data.device_links.to_dict("records"),
        data.network_links.to_dict("records"),
        data.transactions.to_dict("records"),
        data.orders.to_dict("records"),
        data.returns.to_dict("records"),
    )
    result_a = run_pipeline(data)
    result_b = run_pipeline(data_shuffled)
    assert result_a[0]["cluster_id"] == result_b[0]["cluster_id"]
    assert sorted(result_a[0]["customers"]) == sorted(result_b[0]["customers"])


# ----------------------------------------------------------------------
# Edge cases
# ----------------------------------------------------------------------
def test_empty_dataset_returns_no_clusters():
    assert run_pipeline(RawData()) == []


def test_customer_with_single_transaction_and_no_order_is_safe():
    data = _raw_data(
        [
            {"id": "c1", "merchant_id": "m1", "created_at": T0},
            {"id": "c2", "merchant_id": "m1", "created_at": T0},
        ],
        devices=[{"id": "d1", "device_fingerprint": "fp1", "created_at": T0}],
        device_links=[
            {"customer_id": "c1", "device_id": "d1", "first_seen": T0, "last_seen": T0},
            {"customer_id": "c2", "device_id": "d1", "first_seen": T0, "last_seen": T0},
        ],
        transactions=[
            {
                "id": "tx1",
                "customer_id": "c1",
                "device_id": "d1",
                "network_id": None,
                "amount": 50.0,
                "currency": "INR",
                "status": "pending",
                "created_at": T0,
            }
        ],
        # No matching order for tx1 -- must not crash.
    )
    results = run_pipeline(data)
    assert len(results) == 1
    assert results[0]["signals"]["return_anomaly"]["num_orders"] == 0
    assert results[0]["signals"]["return_anomaly"]["return_rate"] is None


def test_no_nan_or_inf_in_pipeline_output():
    data, _ = _suspicious_coordinated_scenario()
    results = run_pipeline(data)
    output_json = json.dumps(results, default=str)
    assert "NaN" not in output_json
    assert "Infinity" not in output_json
