"""TrustGraph detector experiment harness.

Runs M2 candidate generation + M3 scoring directly from deterministic
synthetic DataFrames. This is an experiment/reporting tool only: it does
not modify production detector configuration or use ground truth in the
runtime detection path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.intelligence.data_loader import RawData  # noqa: E402
from app.intelligence.pipeline import run_pipeline  # noqa: E402
from app.risk.config import RiskConfig  # noqa: E402
from app.risk.evaluation import evaluate  # noqa: E402
from app.risk.pipeline import score_clusters  # noqa: E402
from scripts.synthetic.builder import SyntheticDataBuilder  # noqa: E402
from scripts.synthetic.config import GeneratorConfig  # noqa: E402

SEEDS = [42, 43, 44, 45, 46, 9001, 9002, 9003, 9004, 9005]
THRESHOLDS = [20, 30, 40, 50, 60, 70, 80, 90]


def make_raw(frames: dict[str, pd.DataFrame]) -> RawData:
    return RawData(
        customers=frames["customers"],
        devices=frames["devices"],
        networks=frames["ips"],
        device_links=frames["customer_device_links"],
        network_links=frames["customer_network_links"],
        transactions=frames["transactions"],
        orders=frames["orders"],
        returns=frames["returns"],
    )


def run_seed(seed: int, risk_config: RiskConfig | None = None) -> tuple[dict, list, dict]:
    frames = SyntheticDataBuilder(GeneratorConfig(random_seed=seed)).build()
    data = make_raw(frames)
    m2 = run_pipeline(data)
    scored = score_clusters(m2, data, risk_config)
    ground_truth = dict(zip(frames["ground_truth"]["customer_id"], frames["ground_truth"]["is_abuse"]))
    report = evaluate(scored, ground_truth, risk_config)

    abuse_rings = set(frames["ground_truth"].loc[frames["ground_truth"]["is_abuse"], "cluster_id"].dropna())
    candidate_customer_ids = {cid for c in scored for cid in c.customers}
    represented_rings = set()
    for ring in abuse_rings:
        ids = set(frames["ground_truth"].loc[frames["ground_truth"]["cluster_id"] == ring, "customer_id"])
        if ids & candidate_customer_ids:
            represented_rings.add(ring)

    coverage = {
        "abuse_rings_total": len(abuse_rings),
        "abuse_rings_represented": len(represented_rings),
        "abuse_ring_candidate_coverage": round(len(represented_rings) / len(abuse_rings), 4) if abuse_rings else None,
        "abuse_rings_missed_entirely": sorted(abuse_rings - represented_rings),
    }
    return report, scored, coverage


def row(seed: int, report: dict, coverage: dict, level: str = "cluster_level") -> dict:
    cm = report[level]
    return {
        "seed": seed,
        "candidate_clusters": report["summary"]["num_candidate_clusters"],
        "abuse_rings": coverage["abuse_rings_total"],
        "candidate_ring_coverage": coverage["abuse_ring_candidate_coverage"],
        "precision": cm["precision"],
        "recall": cm["recall"],
        "f1": cm["f1"],
        "fpr": cm["false_positive_rate"],
    }


def threshold_rows(seed: int, scored: list, ground_truth: dict, level: str) -> list[dict]:
    out = []
    cfg = RiskConfig()
    for t in THRESHOLDS:
        cfg2 = RiskConfig(default_evaluation_threshold=float(t))
        # Preserve the sweep values but evaluate one operating point at a time.
        rep = evaluate(scored, ground_truth, cfg2)
        cm = rep[level]
        out.append({"seed": seed, "level": level, "threshold": t, **cm})
    return out


def ground_truth_for_seed(seed: int) -> dict[str, bool]:
    frames = SyntheticDataBuilder(GeneratorConfig(random_seed=seed)).build()
    gt = frames["ground_truth"]
    return dict(zip(gt["customer_id"], gt["is_abuse"]))


def ablation(seed: int = 42) -> list[dict]:
    frames = SyntheticDataBuilder(GeneratorConfig(random_seed=seed)).build()
    data = make_raw(frames)
    m2 = run_pipeline(data)
    gt = dict(zip(frames["ground_truth"]["customer_id"], frames["ground_truth"]["is_abuse"]))
    base = RiskConfig()
    names = [
        ("baseline", None),
        ("relationship_zero", "relationship_weight"),
        ("temporal_zero", "temporal_weight"),
        ("velocity_zero", "velocity_weight"),
        ("coordination_zero", "coordination_weight"),
        ("return_zero", "return_anomaly_weight"),
        ("graph_zero", "graph_weight"),
    ]
    rows = []
    for name, attr in names:
        cfg = RiskConfig()
        if attr:
            setattr(cfg, attr, 1e-9)
        scored = score_clusters(m2, data, cfg)
        rep = evaluate(scored, gt, cfg)
        cm = rep["cluster_level"]
        rows.append({"seed": seed, "variant": name, "threshold": 50, **cm})
    return rows


def main() -> None:
    out_dir = ROOT / "artifacts" / "detector_experiments"
    out_dir.mkdir(parents=True, exist_ok=True)

    seed_rows = []
    threshold_rows_all = []
    for seed in SEEDS:
        report, scored, coverage = run_seed(seed)
        seed_rows.append(row(seed, report, coverage, "cluster_level"))
        frames = SyntheticDataBuilder(GeneratorConfig(random_seed=seed)).build()
        gt = dict(zip(frames["ground_truth"]["customer_id"], frames["ground_truth"]["is_abuse"]))
        threshold_rows_all.extend(threshold_rows(seed, scored, gt, "cluster_level"))

    seed_df = pd.DataFrame(seed_rows)
    thresh_df = pd.DataFrame(threshold_rows_all)
    abl_df = pd.DataFrame(ablation(42))

    seed_df.to_csv(out_dir / "seed_generalization.csv", index=False)
    thresh_df.to_csv(out_dir / "threshold_sweep.csv", index=False)
    abl_df.to_csv(out_dir / "signal_ablation_seed42.csv", index=False)

    summary = {
        "seeds": SEEDS,
        "development_seeds": SEEDS[:5],
        "held_out_candidate_seeds": SEEDS[5:],
        "seed_generalization_mean": {
            k: round(float(seed_df[k].mean()), 4)
            for k in ["candidate_ring_coverage", "precision", "recall", "f1", "fpr"]
        },
        "seed_generalization_min": {
            k: round(float(seed_df[k].min()), 4)
            for k in ["candidate_ring_coverage", "precision", "recall", "f1", "fpr"]
        },
        "seed_generalization_max": {
            k: round(float(seed_df[k].max()), 4)
            for k in ["candidate_ring_coverage", "precision", "recall", "f1", "fpr"]
        },
        "note": "9001-9005 are independent fixed seeds for generalization checking, not used to alter production weights in this harness.",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    md = [
        "# TrustGraph Detector Experiment Report",
        "",
        "## Seed generalization (final operating point, cluster level)",
        "",
        seed_df.to_markdown(index=False),
        "",
        "## Signal ablation (seed 42, diagnostic threshold 50)",
        "",
        abl_df.to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        "- This harness does not modify production scoring weights.",
        "- Candidate-ring coverage measures a limitation before scoring: abuse rings with no shared device/network relationship are never scored.",
        "- The 9001-9005 seeds are fixed generalization seeds and should be treated as a future held-out set if they are kept untouched during tuning.",
        "- Ablation here is diagnostic: removing a weight changes the score budget, so it is not a causal feature-importance estimate.",
    ]
    (out_dir / "REPORT.md").write_text("\n".join(md))

    print("Wrote:", out_dir)
    print(seed_df.to_string(index=False))
    print("\nAblation seed 42:")
    print(abl_df.to_string(index=False))


if __name__ == "__main__":
    main()
