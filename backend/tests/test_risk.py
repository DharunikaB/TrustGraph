"""Tests for the M3 risk engine: scoring, exposure, and evaluation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.intelligence.pipeline import run_pipeline
from app.risk.config import RiskConfig, RiskLevel
from app.risk.evaluation import (
    ConfusionMatrix,
    cluster_ground_truth_label,
    cluster_level_confusion_matrix,
    customer_level_confusion_matrix,
    evaluate,
    false_positive_financial_cost,
    load_ground_truth,
    threshold_sweep,
)
from app.risk.exposure import compute_exposure
from app.risk.models import ScoredCluster
from app.risk.pipeline import score_clusters
from app.risk.scoring import compute_risk_assessment
from app.models import Customer, GroundTruth, GroundTruthLabel, Merchant

# Reuse M2's hand-built scenarios rather than duplicating scenario
# construction -- same test data, different questions asked of it.
from tests.test_intelligence import (
    T0,
    _legitimate_shared_infra_scenario,
    _suspicious_coordinated_scenario,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _minimal_signals(**overrides) -> dict:
    """A signals dict with every field at its most 'unremarkable' value.

    Individual tests override just the fields they care about.
    """
    base = {
        "shared_device": {
            "num_devices": 1,
            "device_customer_counts_in_cluster": {"d1": 2},
            "device_customer_counts_dataset_wide": {"d1": 2},
            "max_customers_per_device": 2,
            "shared_device_ratio": 0.0,
        },
        "shared_network": {
            "num_networks": 1,
            "network_customer_counts_in_cluster": {"n1": 2},
            "network_customer_counts_dataset_wide": {"n1": 2},
            "max_customers_per_network": 2,
            "shared_network_ratio": 0.0,
        },
        "account_creation_burst": {
            "num_customers": 2,
            "creation_time_span_hours": 2000.0,
            "max_accounts_in_window": 1,
            "window_hours": 48.0,
            "burst_ratio": 0.0,
        },
        "transaction_velocity": {
            "num_transactions": 4,
            "transactions_per_customer": 2.0,
            "max_transactions_in_window": 1,
            "window_hours": 24.0,
            "activity_span_hours": 500.0,
            "baseline_transactions_per_customer": 2.0,
            "velocity_ratio_vs_baseline": 1.0,
        },
        "transaction_coordination": {
            "num_transactions": 4,
            "temporal_coordination_ratio": 0.0,
            "proximity_window_minutes": 60.0,
            "amount_coefficient_of_variation": 0.5,
            "distinct_amounts_shared_across_customers": 0,
        },
        "return_anomaly": {
            "num_orders": 4,
            "num_returns": 0,
            "return_rate": 0.0,
            "baseline_return_rate": 0.1,
            "deviation_ratio": 0.0,
            "top_customer_return_share": None,
            "insufficient_data": False,
        },
        "graph_connectivity": {
            "num_customer_nodes": 2,
            "num_device_nodes": 1,
            "num_network_nodes": 1,
            "num_edges": 2,  # each customer -> device only, no shared network edge -> tree, 0 redundancy
            "density": 0.5,
            "avg_customer_degree": 1.0,
            "is_connected": True,
            "diameter": 2,
        },
    }
    for key, value in overrides.items():
        base[key] = {**base[key], **value}
    return base


def _maximal_signals() -> dict:
    """A signals dict with every field pushed to its most extreme value."""
    return {
        "shared_device": {
            "num_devices": 1,
            "device_customer_counts_in_cluster": {"d1": 5},
            "device_customer_counts_dataset_wide": {"d1": 5},
            "max_customers_per_device": 5,
            "shared_device_ratio": 1.0,
        },
        "shared_network": {
            "num_networks": 1,
            "network_customer_counts_in_cluster": {"n1": 5},
            "network_customer_counts_dataset_wide": {"n1": 5},
            "max_customers_per_network": 5,
            "shared_network_ratio": 1.0,
        },
        "account_creation_burst": {
            "num_customers": 5,
            "creation_time_span_hours": 2.0,
            "max_accounts_in_window": 5,
            "window_hours": 48.0,
            "burst_ratio": 1.0,
        },
        "transaction_velocity": {
            "num_transactions": 40,
            "transactions_per_customer": 8.0,
            "max_transactions_in_window": 20,
            "window_hours": 24.0,
            "activity_span_hours": 10.0,
            "baseline_transactions_per_customer": 2.0,
            "velocity_ratio_vs_baseline": 4.0,  # excess=3.0, capped at 2.0
        },
        "transaction_coordination": {
            "num_transactions": 40,
            "temporal_coordination_ratio": 1.0,
            "proximity_window_minutes": 60.0,
            "amount_coefficient_of_variation": 0.9,
            "distinct_amounts_shared_across_customers": 3,
        },
        "return_anomaly": {
            "num_orders": 40,
            "num_returns": 30,
            "return_rate": 0.75,
            "baseline_return_rate": 0.1,
            "deviation_ratio": 7.5,  # excess=6.5, capped at 4.0
            "top_customer_return_share": 1.0,
            "insufficient_data": False,
        },
        "graph_connectivity": {
            "num_customer_nodes": 5,
            "num_device_nodes": 1,
            "num_network_nodes": 1,
            "num_edges": 10,  # each customer -> device AND network: 2*5=10 edges, nodes=7, redundancy=10-6=4, ratio=4/4=1.0
            "density": 0.6,
            "avg_customer_degree": 2.0,
            "is_connected": True,
            "diameter": 2,
        },
    }


# ----------------------------------------------------------------------
# 1-3: Score bounds, determinism, level mapping
# ----------------------------------------------------------------------
def test_risk_score_always_within_0_100():
    for signals in (_minimal_signals(), _maximal_signals()):
        assessment = compute_risk_assessment(signals)
        assert 0 <= assessment.score <= 100


def test_same_input_produces_same_score():
    signals = _maximal_signals()
    a = compute_risk_assessment(signals)
    b = compute_risk_assessment(signals)
    assert a.score == b.score
    assert a.level == b.level


def test_risk_level_boundaries_map_correctly():
    config = RiskConfig()
    assert config.risk_level(0) == RiskLevel.LOW
    assert config.risk_level(config.low_max - 0.01) == RiskLevel.LOW
    assert config.risk_level(config.low_max) == RiskLevel.MEDIUM
    assert config.risk_level(config.medium_max - 0.01) == RiskLevel.MEDIUM
    assert config.risk_level(config.medium_max) == RiskLevel.HIGH
    assert config.risk_level(config.high_max - 0.01) == RiskLevel.HIGH
    assert config.risk_level(config.high_max) == RiskLevel.CRITICAL
    assert config.risk_level(100) == RiskLevel.CRITICAL


# ----------------------------------------------------------------------
# 4-5: No single signal dominates; combined evidence does
# ----------------------------------------------------------------------
def test_single_relationship_signal_alone_does_not_produce_high_risk():
    """Full shared-device/network sharing with NOTHING else notable must
    stay well under the HIGH band -- the core TrustGraph principle."""
    config = RiskConfig()
    signals = _minimal_signals(
        shared_device={"shared_device_ratio": 1.0, "max_customers_per_device": 5},
        shared_network={"shared_network_ratio": 1.0, "max_customers_per_network": 5},
    )
    assessment = compute_risk_assessment(signals, config)
    assert assessment.score < config.medium_max  # not even HIGH, let alone CRITICAL
    assert assessment.level in (RiskLevel.LOW, RiskLevel.MEDIUM)


def test_single_burst_signal_alone_does_not_reach_critical():
    config = RiskConfig()
    signals = _minimal_signals(account_creation_burst={"burst_ratio": 1.0, "max_accounts_in_window": 5})
    assessment = compute_risk_assessment(signals, config)
    assert assessment.level != RiskLevel.CRITICAL


def test_multiple_combined_signals_produce_substantially_higher_risk():
    minimal_score = compute_risk_assessment(_minimal_signals()).score
    maximal_score = compute_risk_assessment(_maximal_signals()).score
    assert maximal_score > minimal_score + 40  # a large, clear gap
    assert compute_risk_assessment(_maximal_signals()).level == RiskLevel.CRITICAL


def test_contributor_contributions_never_exceed_their_own_cap():
    for signals in (_minimal_signals(), _maximal_signals()):
        assessment = compute_risk_assessment(signals)
        for c in assessment.contributors:
            assert 0 <= c.contribution <= c.max_contribution + 1e-9


def test_contributors_sum_to_total_score():
    signals = _maximal_signals()
    assessment = compute_risk_assessment(signals)
    total_contribution = sum(c.contribution for c in assessment.contributors)
    assert assessment.score == pytest.approx(min(100, total_contribution), abs=0.01)


# ----------------------------------------------------------------------
# 6-8: Exposure calculation
# ----------------------------------------------------------------------
def test_exposure_calculates_transaction_and_returned_value_correctly():
    data, customer_ids = _suspicious_coordinated_scenario()
    tx_ids = data.transactions["id"].tolist()

    exposure = compute_exposure(tx_ids, data)

    assert exposure.transaction_count == 4
    expected_tx_value = round(float(data.transactions["amount"].sum()), 2)
    assert exposure.transaction_value == expected_tx_value

    expected_returned = round(float(data.returns["amount"].sum()), 2)
    assert exposure.returned_value == expected_returned
    assert exposure.return_count == 3


def test_estimated_exposure_is_returned_value_not_transaction_value():
    """The exposure model must never conflate 'money that moved' with
    'money lost' -- estimated_exposure is specifically the returned
    value, never the full transaction value."""
    data, _ = _suspicious_coordinated_scenario()
    tx_ids = data.transactions["id"].tolist()
    exposure = compute_exposure(tx_ids, data)

    assert exposure.estimated_exposure == exposure.returned_value
    assert exposure.estimated_exposure < exposure.transaction_value


def test_exposure_handles_empty_transaction_list():
    data, _ = _legitimate_shared_infra_scenario()
    exposure = compute_exposure([], data)
    assert exposure.transaction_count == 0
    assert exposure.transaction_value == 0.0
    assert exposure.estimated_exposure == 0.0


# ----------------------------------------------------------------------
# 9-12: Precision / recall / F1 / false-positive rate correctness
# ----------------------------------------------------------------------
def test_confusion_matrix_metrics_hand_verified():
    # TP=3, FP=1, TN=5, FN=2
    cm = ConfusionMatrix(true_positives=3, false_positives=1, true_negatives=5, false_negatives=2)
    assert cm.precision == pytest.approx(3 / 4, abs=1e-4)
    assert cm.recall == pytest.approx(3 / 5, abs=1e-4)
    assert cm.f1 == pytest.approx(2 * (3 / 4) * (3 / 5) / ((3 / 4) + (3 / 5)), abs=1e-4)
    assert cm.accuracy == pytest.approx((3 + 5) / 11, abs=1e-4)
    assert cm.false_positive_rate == pytest.approx(1 / 6, abs=1e-4)


def test_confusion_matrix_handles_zero_denominators():
    cm = ConfusionMatrix(true_positives=0, false_positives=0, true_negatives=5, false_negatives=0)
    assert cm.precision is None  # no positive predictions at all
    assert cm.recall is None  # no actual positives at all... wait FN=0 too
    assert cm.f1 is None


def test_confusion_matrix_all_zero_is_safe():
    cm = ConfusionMatrix(0, 0, 0, 0)
    assert cm.precision is None
    assert cm.recall is None
    assert cm.f1 is None
    assert cm.accuracy is None
    assert cm.false_positive_rate is None


# ----------------------------------------------------------------------
# 13: Threshold evaluation
# ----------------------------------------------------------------------
def _scored_cluster(cluster_id: str, customer_ids: list[str], score: float) -> ScoredCluster:
    from app.risk.models import Contributor, ExposureAssessment, RiskAssessment

    config = RiskConfig()
    return ScoredCluster(
        cluster_id=cluster_id,
        customers=customer_ids,
        devices=["d1"],
        networks=["n1"],
        transactions=[],
        risk=RiskAssessment(
            score=score,
            level=config.risk_level(score),
            contributors=[Contributor(signal="test", contribution=score, max_contribution=100, evidence="synthetic")],
        ),
        exposure=ExposureAssessment(
            transaction_count=10,
            transaction_value=1000.0,
            order_count=10,
            return_count=1,
            returned_value=100.0,
            estimated_exposure=100.0,
        ),
        signals={},
        evidence=[],
    )


def test_threshold_sweep_extremes_behave_correctly():
    clusters = [
        _scored_cluster("c1", ["a1", "a2"], score=90.0),  # abuse, high score
        _scored_cluster("c2", ["b1", "b2"], score=10.0),  # legit, low score
    ]
    ground_truth = {"a1": True, "a2": True, "b1": False, "b2": False}
    config = RiskConfig(threshold_sweep=(0.0, 50.0, 100.0))

    sweep = threshold_sweep(clusters, ground_truth, config, level="cluster")
    by_threshold = {row["threshold"]: row for row in sweep}

    # threshold 0: everything flagged -> perfect recall, but c2 is a FP
    assert by_threshold[0.0]["recall"] == 1.0
    assert by_threshold[0.0]["false_positives"] == 1

    # threshold 100: nothing flagged (scores are 90 and 10, neither >=100)
    assert by_threshold[100.0]["true_positives"] == 0
    assert by_threshold[100.0]["recall"] == 0.0

    # threshold 50: only c1 flagged -> perfect precision and recall
    assert by_threshold[50.0]["precision"] == 1.0
    assert by_threshold[50.0]["recall"] == 1.0


def test_threshold_sweep_invalid_level_raises():
    with pytest.raises(ValueError):
        threshold_sweep([], {}, RiskConfig(), level="nonsense")


# ----------------------------------------------------------------------
# 14: Ground truth used only in evaluation
# ----------------------------------------------------------------------
def test_ground_truth_never_imported_by_detection_path():
    risk_dir = Path(__file__).resolve().parents[1] / "app" / "risk"
    forbidden = ["import GroundTruth", "GroundTruth(", "GroundTruthLabel.", "select(GroundTruth"]
    detection_files = ["config.py", "scoring.py", "exposure.py", "models.py", "pipeline.py"]

    for filename in detection_files:
        content = (risk_dir / filename).read_text()
        for pattern in forbidden:
            assert pattern not in content, f"{filename} references forbidden pattern {pattern!r}"


def test_evaluation_is_the_only_module_touching_ground_truth():
    """Same precise-usage check as the detection-path test above, but
    scanning every file in app/risk (not just the detection-path ones) --
    a bare substring match on "GroundTruth" would false-positive on this
    module's own safety-documentation docstrings (e.g. pipeline.py's
    "this module never imports GroundTruth" explanation).
    """
    risk_dir = Path(__file__).resolve().parents[1] / "app" / "risk"
    forbidden = ["import GroundTruth", "GroundTruth(", "GroundTruthLabel.", "select(GroundTruth"]
    files_with_ground_truth_usage = []
    for py_file in risk_dir.glob("*.py"):
        if py_file.name == "evaluation.py":
            continue
        content = py_file.read_text()
        if any(pattern in content for pattern in forbidden):
            files_with_ground_truth_usage.append(py_file.name)
    assert files_with_ground_truth_usage == []


@pytest.mark.asyncio
async def test_load_ground_truth_end_to_end(async_session):
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

    ground_truth = await load_ground_truth(async_session)
    assert ground_truth[customer.id] is True


# ----------------------------------------------------------------------
# 16-18: Empty datasets, single-cluster edge cases, NaN/Infinity safety
# ----------------------------------------------------------------------
def test_empty_cluster_list_scores_safely():
    assert score_clusters([], _legitimate_shared_infra_scenario()[0]) == []


def test_evaluate_with_no_clusters_is_safe():
    report = evaluate([], {})
    assert report["cluster_level"]["true_positives"] == 0
    assert report["cluster_level"]["precision"] is None
    output_json = json.dumps(report, default=str)
    assert "NaN" not in output_json
    assert "Infinity" not in output_json


def test_evaluate_with_single_cluster_is_safe():
    clusters = [_scored_cluster("c1", ["a1"], score=80.0)]
    ground_truth = {"a1": True}
    report = evaluate(clusters, ground_truth)
    assert report["cluster_level"]["true_positives"] == 1
    assert report["summary"]["num_candidate_clusters"] == 1


def test_no_nan_or_infinity_in_scored_cluster_output():
    data, customer_ids = _suspicious_coordinated_scenario()
    m2_results = run_pipeline(data)
    scored = score_clusters(m2_results, data)
    output_json = json.dumps([c.model_dump() for c in scored], default=str)
    assert "NaN" not in output_json
    assert "Infinity" not in output_json


def test_cluster_ground_truth_label_none_when_no_data():
    cluster = _scored_cluster("c1", ["unknown-customer"], score=50.0)
    label = cluster_ground_truth_label(cluster, {}, RiskConfig())
    assert label is None


# ----------------------------------------------------------------------
# 19: Different random seeds / configurations can be evaluated
# ----------------------------------------------------------------------
def test_scoring_methodology_runs_on_a_different_synthetic_seed():
    """Generalization check: the SAME scoring config, unmodified, must
    run cleanly on a differently-seeded (and differently-shaped)
    synthetic dataset without crashing or producing invalid output --
    it must not be silently tuned to the exact default dataset."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.synthetic.builder import SyntheticDataBuilder
    from scripts.synthetic.config import GeneratorConfig
    from app.intelligence.data_loader import RawData

    gen_config = GeneratorConfig(
        random_seed=999,
        merchant_count=2,
        normal_customer_count=80,
        shared_infra_customer_count=40,
        abuse_customer_count=30,
    )
    frames = SyntheticDataBuilder(gen_config).build()

    raw = RawData(
        customers=frames["customers"][["id", "merchant_id", "created_at"]],
        devices=frames["devices"][["id", "device_fingerprint", "created_at"]],
        networks=frames["ips"][["id", "ip_address", "created_at"]],
        device_links=frames["customer_device_links"][["customer_id", "device_id", "first_seen", "last_seen"]],
        network_links=frames["customer_network_links"][["customer_id", "network_id", "first_seen", "last_seen"]],
        transactions=frames["transactions"][
            ["id", "customer_id", "device_id", "network_id", "amount", "currency", "status", "created_at"]
        ],
        orders=frames["orders"][["id", "transaction_id", "order_amount", "created_at"]],
        returns=frames["returns"][["id", "order_id", "amount", "reason", "created_at"]],
    )

    m2_results = run_pipeline(raw)
    scored = score_clusters(m2_results, raw)

    assert len(scored) > 0
    for cluster in scored:
        assert 0 <= cluster.risk.score <= 100

    ground_truth = dict(zip(frames["ground_truth"]["customer_id"], frames["ground_truth"]["is_abuse"]))
    report = evaluate(scored, ground_truth)
    assert report["summary"]["num_candidate_clusters"] == len(scored)
    output_json = json.dumps(report, default=str)
    assert "NaN" not in output_json and "Infinity" not in output_json


# ----------------------------------------------------------------------
# 20: Legitimate shared infrastructure is not automatically abuse
# ----------------------------------------------------------------------
def test_legitimate_shared_infra_scores_low():
    data, customer_ids = _legitimate_shared_infra_scenario()
    m2_results = run_pipeline(data)
    scored = score_clusters(m2_results, data)

    assert len(scored) == 1
    cluster = scored[0]
    config = RiskConfig()
    # Full sharing, spread-out creation, independent amounts, ordinary
    # returns -- should land LOW or at worst low MEDIUM, never HIGH/CRITICAL.
    assert cluster.risk.level in (RiskLevel.LOW, RiskLevel.MEDIUM)
    assert cluster.risk.score < config.high_max


def test_suspicious_coordinated_pattern_scores_meaningfully_higher():
    legit_data, _ = _legitimate_shared_infra_scenario()
    legit_scored = score_clusters(run_pipeline(legit_data), legit_data)

    sus_data, _ = _suspicious_coordinated_scenario()
    sus_scored = score_clusters(run_pipeline(sus_data), sus_data)

    assert sus_scored[0].risk.score > legit_scored[0].risk.score
