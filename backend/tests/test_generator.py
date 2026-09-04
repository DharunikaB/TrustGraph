"""Tests for the synthetic data generator.

Covers the specific requirements called out in the M1 spec:
reproducibility, preserved ground truth, no ground-truth leakage into
feature tables, referential integrity across generated tables, and
that shared devices/IPs are NOT a perfect predictor of abuse (i.e. the
dataset actually poses a real classification problem).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from scripts.synthetic.builder import SyntheticDataBuilder
from scripts.synthetic.config import GeneratorConfig


def _small_config(seed: int = 1) -> GeneratorConfig:
    return GeneratorConfig(
        random_seed=seed,
        merchant_count=2,
        normal_customer_count=40,
        shared_infra_customer_count=20,
        abuse_customer_count=15,
    )


def test_reproducible_with_same_seed():
    frames_a = SyntheticDataBuilder(_small_config(seed=7)).build()
    frames_b = SyntheticDataBuilder(_small_config(seed=7)).build()

    for name in frames_a:
        assert frames_a[name].equals(frames_b[name]), f"{name} differs between identical-seed runs"


def test_different_seed_gives_different_data():
    frames_a = SyntheticDataBuilder(_small_config(seed=1)).build()
    frames_b = SyntheticDataBuilder(_small_config(seed=2)).build()

    assert not frames_a["transactions"]["amount"].equals(frames_b["transactions"]["amount"])


def test_ground_truth_counts_match_config():
    config = _small_config()
    frames = SyntheticDataBuilder(config).build()
    gt = frames["ground_truth"]

    assert (gt["label"] == "normal").sum() == config.normal_customer_count
    assert (gt["label"] == "legitimate_shared_infra").sum() == config.shared_infra_customer_count
    assert (gt["label"] == "coordinated_abuse").sum() == config.abuse_customer_count
    assert len(gt) == len(frames["customers"])


def test_ground_truth_not_leaked_into_feature_tables():
    frames = SyntheticDataBuilder(_small_config()).build()
    leak_columns = {"label", "cluster_id", "is_abuse"}

    for name in ("customers", "transactions", "orders", "returns", "devices", "ips"):
        assert leak_columns.isdisjoint(frames[name].columns), (
            f"{name} table must not contain ground-truth columns"
        )


def test_referential_integrity():
    frames = SyntheticDataBuilder(_small_config()).build()

    merchant_ids = set(frames["merchants"]["id"])
    customer_ids = set(frames["customers"]["id"])
    device_ids = set(frames["devices"]["id"])
    ip_ids = set(frames["ips"]["id"])
    transaction_ids = set(frames["transactions"]["id"])
    order_ids = set(frames["orders"]["id"])

    assert set(frames["customers"]["merchant_id"]).issubset(merchant_ids)
    assert set(frames["customer_device_links"]["customer_id"]).issubset(customer_ids)
    assert set(frames["customer_device_links"]["device_id"]).issubset(device_ids)
    assert set(frames["customer_network_links"]["customer_id"]).issubset(customer_ids)
    assert set(frames["customer_network_links"]["network_id"]).issubset(ip_ids)
    assert set(frames["transactions"]["customer_id"]).issubset(customer_ids)
    assert set(frames["orders"]["transaction_id"]).issubset(transaction_ids)
    assert set(frames["returns"]["order_id"]).issubset(order_ids)
    assert set(frames["ground_truth"]["customer_id"]).issubset(customer_ids)


def test_ip_and_device_ids_are_globally_unique():
    """Every generated device/IP row must have a unique fingerprint/address
    (a random collision should be deduped into one row, never inserted
    twice) -- otherwise loading into PostgreSQL violates the unique
    constraint on those columns.
    """
    frames = SyntheticDataBuilder(_small_config()).build()

    assert frames["devices"]["device_fingerprint"].is_unique
    assert frames["ips"]["ip_address"].is_unique
    assert frames["devices"]["id"].is_unique
    assert frames["ips"]["id"].is_unique


def test_shared_device_is_not_a_perfect_abuse_signal():
    """A device used by more than one customer must show up on BOTH
    sides of the ground truth -- otherwise "shared device" would be a
    trivial, perfectly-separating feature, which the spec explicitly
    forbids.
    """
    config = GeneratorConfig(
        random_seed=3,
        merchant_count=2,
        normal_customer_count=100,
        shared_infra_customer_count=120,
        abuse_customer_count=80,
        shared_infra_share_device_prob=1.0,
        abuse_share_device_prob=1.0,
    )
    frames = SyntheticDataBuilder(config).build()

    gt = frames["ground_truth"].set_index("customer_id")
    links = frames["customer_device_links"].merge(gt, on="customer_id")

    device_customer_counts = links.groupby("device_id")["customer_id"].nunique()
    shared_device_ids = device_customer_counts[device_customer_counts > 1].index
    shared = links[links["device_id"].isin(shared_device_ids)]

    labels_on_shared_devices = set(shared["label"].unique())
    assert "legitimate_shared_infra" in labels_on_shared_devices
    assert "coordinated_abuse" in labels_on_shared_devices


def test_amounts_and_transactions_are_positive():
    frames = SyntheticDataBuilder(_small_config()).build()
    assert (frames["transactions"]["amount"] > 0).all()
    assert (frames["orders"]["order_amount"] > 0).all()
    if len(frames["returns"]) > 0:
        assert (frames["returns"]["amount"] > 0).all()
