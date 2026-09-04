"""Train the promoted TrustGraph GBM artifact from development seeds only.

This script is training/evaluation infrastructure, not runtime detection logic.
Ground truth is accessed only here through app.risk.evaluation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
import joblib

from app.db.session import engine, AsyncSessionLocal
from app.ml.features import FEATURE_NAMES, cluster_to_features
from app.risk.config import RiskConfig
from app.risk.evaluation import cluster_ground_truth_label, load_ground_truth
from app.risk.pipeline import run_risk_pipeline_async

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "synthetic"
GENERATOR = ROOT / "scripts" / "generate_synthetic_data.py"
LOADER = ROOT / "scripts" / "load_data.py"
OUTPUT = ROOT / "artifacts" / "ml_model" / "trustgraph_gbm.joblib"
SEEDS = [42, 43, 44, 45, 46]


def run(cmd: list[str]) -> None:
    print("$", " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=ROOT, check=True)


def build_model() -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                GradientBoostingClassifier(
                    random_state=20260903,
                    n_estimators=150,
                    learning_rate=0.05,
                    max_depth=3,
                ),
            ),
        ]
    )


async def collect_seed() -> tuple[list[list[float]], list[int]]:
    async with AsyncSessionLocal() as session:
        clusters = list(await run_risk_pipeline_async(session=session))
        truth = await load_ground_truth(session)
    config = RiskConfig()
    X: list[list[float]] = []
    y: list[int] = []
    for cluster in clusters:
        label = cluster_ground_truth_label(cluster, truth, config)
        if label is None:
            continue
        X.append(cluster_to_features(cluster))
        y.append(int(label))
    return X, y


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-generation", action="store_true")
    args = parser.parse_args()

    all_X: list[list[float]] = []
    all_y: list[int] = []
    python = sys.executable

    for seed in SEEDS:
        print(f"\n=== DEVELOPMENT SEED {seed} ===")
        if not args.skip_generation:
            run([python, str(GENERATOR), "--seed", str(seed), "--out", str(DATA_DIR)])
            run([python, str(LOADER), "--input", str(DATA_DIR), "--reset"])
            await engine.dispose()
        X, y = await collect_seed()
        print(f"labelled clusters: {len(y)} | positives: {sum(y)} | negatives: {len(y)-sum(y)}")
        all_X.extend(X)
        all_y.extend(y)

    if len(set(all_y)) < 2:
        raise RuntimeError("Development population must contain both classes")

    model = build_model()
    model.fit(all_X, all_y)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": model,
        "feature_names": FEATURE_NAMES,
        "model_name": "GradientBoostingClassifier",
        "training_seeds": SEEDS,
        "training_rows": len(all_y),
        "positive_rows": sum(all_y),
        "negative_rows": len(all_y) - sum(all_y),
        "ml_threshold": 0.37,
        "deterministic_threshold": 52.0,
        "role": "secondary_validation_and_candidate_prioritization",
        "ground_truth_used_only_during_training": True,
    }
    joblib.dump(artifact, OUTPUT)
    metadata = {k: v for k, v in artifact.items() if k != "model"}
    OUTPUT.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nSaved ML artifact: {OUTPUT}")
    print(f"Rows: {len(all_y)} | positives: {sum(all_y)} | negatives: {len(all_y)-sum(all_y)}")

    # Restore the canonical demo dataset.
    run([python, str(GENERATOR), "--seed", "42", "--out", str(DATA_DIR)])
    run([python, str(LOADER), "--input", str(DATA_DIR), "--reset"])
    await engine.dispose()
    print("Seed 42 restored.")


if __name__ == "__main__":
    asyncio.run(main())
