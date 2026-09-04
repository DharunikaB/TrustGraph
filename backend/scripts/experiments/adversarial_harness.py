"""TrustGraph LAB — adversarial evaluation harness."""
from __future__ import annotations

import asyncio
import copy
import random
import subprocess
import sys
from dataclasses import dataclass, asdict
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import AsyncSessionLocal, engine
from app.intelligence.config import IntelligenceConfig
from app.intelligence.data_loader import RawData, load_raw_data
from app.intelligence.pipeline import run_pipeline
from app.risk.config import RiskConfig
from app.risk.evaluation import evaluate, load_ground_truth
from app.risk.pipeline import score_clusters

DATA_DIR = BACKEND_DIR / "data" / "synthetic"
GENERATE_SCRIPT = BACKEND_DIR / "scripts" / "generate_synthetic_data.py"
LOAD_SCRIPT = BACKEND_DIR / "scripts" / "load_data.py"
DEV_SEEDS = [42, 43, 44, 45, 46]
HELD_OUT_SEEDS = [9001, 9002, 9003, 9004, 9005]
EXPERIMENT_RANDOM_SEED = 20260903

@dataclass
class Result:
    seed: int
    split: str
    attack: str
    candidate_clusters: int
    precision: float | None
    recall: float | None
    f1: float | None
    fpr: float | None
    customer_precision: float | None
    customer_recall: float | None
    customer_f1: float | None
    customer_fpr: float | None
    abuse_customer_coverage: float | None
    flagged_transaction_value: float | None


def regenerate_and_load(seed: int) -> None:
    print(f"Generating synthetic dataset seed={seed}...")
    subprocess.run([
        sys.executable, str(GENERATE_SCRIPT),
        "--seed", str(seed), "--out", str(DATA_DIR)
    ], cwd=BACKEND_DIR, check=True)
    print("Loading generated dataset into TrustGraph database...")
    subprocess.run([
        sys.executable, str(LOAD_SCRIPT),
        "--input", str(DATA_DIR), "--reset"
    ], cwd=BACKEND_DIR, check=True)


async def reset_engine() -> None:
    await engine.dispose()


def safe_float(x):
    if x is None:
        return None
    try:
        x = float(x)
        return None if np.isnan(x) else x
    except (TypeError, ValueError):
        return None


def abuse_ids(gt: dict[str, bool]) -> set[str]:
    return {cid for cid, abuse in gt.items() if abuse}


def amount_randomization(data: RawData, gt, rng) -> RawData:
    v = copy.deepcopy(data)
    ids = abuse_ids(gt)
    tx = v.transactions.copy()
    mask = tx["customer_id"].isin(ids)

    def change(x):
        if x is None or pd.isna(x):
            return x
        amount = x if isinstance(x, Decimal) else Decimal(str(x))
        multiplier = Decimal(str(rng.uniform(0.98, 1.02)))
        return amount * multiplier

    tx.loc[mask, "amount"] = tx.loc[mask, "amount"].map(change)
    v.transactions = tx
    return v


def infrastructure_rotation(data: RawData, gt, rng) -> RawData:
    v = copy.deepcopy(data)
    ids = abuse_ids(gt)
    devices = v.devices.copy()
    networks = v.networks.copy()
    dl = v.device_links.copy()
    nl = v.network_links.copy()
    tx = v.transactions.copy()

    existing_d = set(devices["id"].astype(str))
    existing_n = set(networks["id"].astype(str))

    for cid in ids:
        did = f"adv_device_{cid}"
        nid = f"adv_network_{cid}"
        if did not in existing_d:
            devices = pd.concat([devices, pd.DataFrame([{
                "id": did,
                "device_fingerprint": f"adv_fp_{cid}_{rng.randint(1,999999)}",
                "created_at": pd.Timestamp.utcnow(),
            }])], ignore_index=True)
            existing_d.add(did)
        if nid not in existing_n:
            networks = pd.concat([networks, pd.DataFrame([{
                "id": nid,
                "ip_address": f"198.51.100.{rng.randint(1,254)}",
                "created_at": pd.Timestamp.utcnow(),
            }])], ignore_index=True)
            existing_n.add(nid)
        m = dl["customer_id"] == cid
        dl.loc[m, "device_id"] = did
        m = nl["customer_id"] == cid
        nl.loc[m, "network_id"] = nid
        m = tx["customer_id"] == cid
        tx.loc[m, "device_id"] = did
        tx.loc[m, "network_id"] = nid

    v.devices, v.networks = devices, networks
    v.device_links, v.network_links = dl, nl
    v.transactions = tx
    return v


def high_fanout_camouflage(data: RawData, gt, rng) -> RawData:
    v = copy.deepcopy(data)
    bad = sorted(abuse_ids(gt))
    good = [cid for cid, abuse in gt.items() if not abuse]
    if not bad or not good:
        return v
    anchor = bad[0]
    dl, nl = v.device_links.copy(), v.network_links.copy()
    ds = dl.loc[dl.customer_id == anchor, "device_id"].dropna().astype(str).unique()
    ns = nl.loc[nl.customer_id == anchor, "network_id"].dropna().astype(str).unique()
    if len(ds) == 0 or len(ns) == 0:
        return v
    rng.shuffle(good)
    now = pd.Timestamp.utcnow()
    for cid in good[:12]:
        dl = pd.concat([dl, pd.DataFrame([{
            "customer_id": cid, "device_id": ds[0],
            "first_seen": now, "last_seen": now,
        }])], ignore_index=True)
        nl = pd.concat([nl, pd.DataFrame([{
            "customer_id": cid, "network_id": ns[0],
            "first_seen": now, "last_seen": now,
        }])], ignore_index=True)
    v.device_links, v.network_links = dl, nl
    return v


def temporal_spreading(data: RawData, gt, rng) -> RawData:
    v = copy.deepcopy(data)
    tx = v.transactions.copy()
    tx["created_at"] = pd.to_datetime(tx["created_at"])
    mask = tx["customer_id"].isin(abuse_ids(gt))
    idx = tx.index[mask]
    tx.loc[idx, "created_at"] = [
        t + pd.Timedelta(hours=rng.uniform(-12, 12))
        for t in tx.loc[idx, "created_at"]
    ]
    v.transactions = tx
    return v


def low_and_slow(data: RawData, gt, rng) -> RawData:
    v = copy.deepcopy(data)
    tx = v.transactions.copy()
    tx["created_at"] = pd.to_datetime(tx["created_at"])
    for cid in abuse_ids(gt):
        mask = tx["customer_id"] == cid
        part = tx.loc[mask].sort_values("created_at")
        if len(part) <= 1:
            continue
        current = part["created_at"].iloc[0]
        times = [current]
        for _ in range(1, len(part)):
            current += pd.Timedelta(hours=rng.uniform(2, 8))
            times.append(current)
        tx.loc[part.index, "created_at"] = times
    v.transactions = tx
    return v


ATTACKS = {
    "baseline": lambda d, g, r: copy.deepcopy(d),
    "amount_randomization": amount_randomization,
    "infrastructure_rotation": infrastructure_rotation,
    "high_fanout_camouflage": high_fanout_camouflage,
    "temporal_spreading": temporal_spreading,
    "low_and_slow": low_and_slow,
}


async def evaluate_variant(data, gt, ic, rc, seed, split, attack):
    m2 = run_pipeline(data, ic)
    scored = score_clusters(m2, data, rc)
    report = evaluate(scored, gt, rc)
    cm = report["cluster_level"]
    cust = report["customer_level"]
    summary = report["summary"]
    return Result(
        seed=seed, split=split, attack=attack,
        candidate_clusters=summary["num_candidate_clusters"],
        precision=safe_float(cm["precision"]),
        recall=safe_float(cm["recall"]),
        f1=safe_float(cm["f1"]),
        fpr=safe_float(cm["false_positive_rate"]),
        customer_precision=safe_float(cust["precision"]),
        customer_recall=safe_float(cust["recall"]),
        customer_f1=safe_float(cust["f1"]),
        customer_fpr=safe_float(cust["false_positive_rate"]),
        abuse_customer_coverage=safe_float(cust["recall"]),
        flagged_transaction_value=safe_float(summary["total_flagged_transaction_value"]),
    )


async def run_seed(seed: int, split: str):
    print("\n" + "=" * 78)
    print(f"SEED {seed} — {split}")
    print("=" * 78)
    regenerate_and_load(seed)
    await reset_engine()

    async with AsyncSessionLocal() as session:
        data = await load_raw_data(session)
        gt = await load_ground_truth(session)

    print(f"Customers      : {len(data.customers)}")
    print(f"Transactions   : {len(data.transactions)}")
    print(f"Ground truth   : {len(gt)}")

    ic, rc = IntelligenceConfig(), RiskConfig()
    baseline_candidates = len(run_pipeline(data, ic))
    print(f"Baseline candidates : {baseline_candidates}")

    results = []
    for name, attack in ATTACKS.items():
        print(f"\n  → {name.upper()}")
        rng = random.Random(EXPERIMENT_RANDOM_SEED + seed + sum(map(ord, name)))
        variant = attack(data, gt, rng)
        result = await evaluate_variant(variant, gt, ic, rc, seed, split, name)
        results.append(result)
        for label, value in [
            ("candidates", result.candidate_clusters),
            ("precision", result.precision), ("recall", result.recall),
            ("F1", result.f1), ("FPR", result.fpr),
            ("coverage", result.abuse_customer_coverage),
        ]:
            print(f"     {label:<10}: {value if value is None else (f'{value:.4f}' if isinstance(value, float) else value)}")
    return results


def write_report(df: pd.DataFrame, path: Path):
    agg = df.groupby(["split", "attack"], as_index=False).mean(numeric_only=True)
    lines = [
        "# TrustGraph — Adversarial Evaluation",
        "",
        "LAB-only controlled stress test of the existing M2/M3 detector.",
        "",
        "## Attack patterns",
        "",
        "1. Amount randomization (±2%).",
        "2. Infrastructure rotation (fresh device/network identifiers).",
        "3. High-fanout camouflage (12 legitimate customers attached to abuse infrastructure).",
        "4. Temporal spreading (±12 hours).",
        "5. Low-and-slow coordination (2–8 hour gaps).",
        "",
        "## Methodology",
        "",
        "- Every attack starts from a fresh in-memory copy of the clean dataset.",
        "- Ground truth is unchanged and used only by the evaluation path.",
        "- M2 candidate generation is unchanged.",
        "- M3 deterministic risk scoring is unchanged.",
        "- Results are controlled synthetic-data stress tests, not production performance.",
        "",
        "## Aggregate results",
        "",
        "| Split | Attack | Candidates | Precision | Recall | F1 | FPR | Customer Recall |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in agg.itertuples(index=False):
        def f(x): return "n/a" if pd.isna(x) else f"{x:.4f}"
        lines.append(f"| {r.split} | {r.attack} | {r.candidate_clusters:.1f} | {f(r.precision)} | {f(r.recall)} | {f(r.f1)} | {f(r.fpr)} | {f(r.customer_recall)} |")
    lines += ["", "## Promotion rule", "", "No mitigation is promoted solely because it helps one attack. A change must improve held-out behavior without unacceptable false-positive growth, candidate explosion, or instability."]
    path.write_text("\n".join(lines), encoding="utf-8")


async def main():
    results = []
    try:
        for split, seed in [("development", s) for s in DEV_SEEDS] + [("held_out", s) for s in HELD_OUT_SEEDS]:
            results.extend(await run_seed(seed, split))
        out = BACKEND_DIR / "artifacts" / "adversarial_experiments"
        out.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([asdict(r) for r in results])
        csv = out / "adversarial_multiseed.csv"
        report = out / "ADVERSARIAL_EVALUATION.md"
        df.to_csv(csv, index=False)
        write_report(df, report)
        print("\n" + "=" * 78)
        print("ADVERSARIAL EVALUATION COMPLETE")
        print("=" * 78)
        print(f"Rows written : {len(df)}")
        print(f"CSV          : {csv}")
        print(f"Report       : {report}")
    finally:
        print("\nRestoring normal TrustGraph seed 42...")
        regenerate_and_load(42)
        await reset_engine()
        print("Seed 42 restoration complete.")


if __name__ == "__main__":
    asyncio.run(main())
