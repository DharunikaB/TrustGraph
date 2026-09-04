"""
TrustGraph — 2-Hop Graph Experiment
====================================

LAB-ONLY experiment.

Question:
    Does filtered 2-hop customer reasoning add useful information
    beyond TrustGraph's existing Customer <-> Device/Network
    connected-component candidate generation?

Important boundaries:
    - M2 never sees ground truth.
    - M3 never sees ground truth.
    - Ground truth is used only for evaluation.
    - Production detector code is NOT modified.
    - This experiment restores seed 42 when finished.

Experiment:
    1. Generate synthetic seed.
    2. Load seed into LAB database.
    3. Load observable RawData.
    4. Run M2.
    5. Run M3 scoring.
    6. Generate observable 2-hop customer pairs.
    7. Apply:
         a. intermediary degree filter
         b. 48h temporal filter
         c. behavioral corroboration
    8. Determine whether pairs are already inside M2 components.
    9. Evaluate V1 M3 detector using evaluation-only ground truth.
   10. Repeat across development and held-out seeds.
   11. Write CSV + Markdown report.
   12. Restore seed 42.
"""

from __future__ import annotations

import asyncio
import csv
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.intelligence.config import IntelligenceConfig
from app.intelligence.data_loader import RawData, load_raw_data
from app.intelligence.pipeline import run_pipeline
from app.risk.config import RiskConfig
from app.risk.evaluation import (
    cluster_ground_truth_label,
    load_ground_truth,
)
from app.risk.pipeline import score_clusters


# ============================================================================
# CONFIG
# ============================================================================

BASE_DIR = Path(__file__).resolve().parents[2]

EXPERIMENT_DATA = BASE_DIR / "data" / "two_hop_experiment"
ARTIFACT_DIR = BASE_DIR / "artifacts" / "two_hop_experiments"

RESULTS_CSV = ARTIFACT_DIR / "two_hop_multiseed.csv"
REPORT_MD = ARTIFACT_DIR / "TWO_HOP_MULTISEED.md"

DEVELOPMENT_SEEDS = [42, 43, 44, 45, 46]
HELD_OUT_SEEDS = [9001, 9002, 9003, 9004, 9005]

# Existing TrustGraph operating point.
DETECTOR_THRESHOLD = 52.0

# 2-hop experiment parameters.
MAX_INTERMEDIARY_DEGREE = 8
TEMPORAL_WINDOW_HOURS = 48.0
BEHAVIOR_WINDOW_HOURS = 24.0

# Deliberately broader experiment-level tolerance.
# This is NOT the production 0.5% detector tolerance.
EXPERIMENT_AMOUNT_TOLERANCE = 0.05

MIN_BEHAVIORAL_SIGNALS = 1

DATABASE_URL = get_settings().DATABASE_URL


# ============================================================================
# RESULT MODEL
# ============================================================================


@dataclass
class SeedResult:
    seed: int
    split: str

    candidate_clusters: int
    labelled_clusters: int
    positive_clusters: int
    negative_clusters: int

    v1_precision: float
    v1_recall: float
    v1_f1: float
    v1_fpr: float

    raw_two_hop_pairs: int
    degree_filtered_pairs: int
    temporal_filtered_pairs: int
    behavior_filtered_pairs: int

    same_component_pairs: int
    cross_component_pairs: int

    unique_customers: int

    abuse_customers: int
    legitimate_customers: int

    abuse_pairs: int
    legitimate_pairs: int
    mixed_pairs: int

    abuse_customer_coverage: float


# ============================================================================
# DATABASE
# ============================================================================


def create_engine():
    """
    Disable asyncpg prepared-statement caching because every seed reload
    drops/recreates the database schema.
    """

    return create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )


# ============================================================================
# COMMAND HELPERS
# ============================================================================


def run_command(command: list[str]) -> None:
    print()
    print("$", " ".join(str(x) for x in command))

    subprocess.run(
        command,
        cwd=str(BASE_DIR),
        check=True,
    )


def generate_seed(seed: int, output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_command(
        [
            sys.executable,
            "scripts/generate_synthetic_data.py",
            "--seed",
            str(seed),
            "--out",
            str(output_dir),
        ]
    )


def load_seed(output_dir: Path) -> None:
    run_command(
        [
            sys.executable,
            "scripts/load_data.py",
            "--input",
            str(output_dir),
            "--reset",
        ]
    )


def restore_seed_42() -> None:
    print()
    print("=" * 72)
    print("RESTORING SEED 42")
    print("=" * 72)

    run_command(
        [
            sys.executable,
            "scripts/load_data.py",
            "--input",
            str(BASE_DIR / "data" / "synthetic"),
            "--reset",
        ]
    )

    print()
    print("Seed 42 restoration complete.")


# ============================================================================
# BASIC HELPERS
# ============================================================================


def safe_float(value, default: float = 0.0) -> float:
    try:
        value = float(value)

        if value != value:
            return default

        return value
    except (TypeError, ValueError):
        return default


def amounts_similar(
    amount_a: float,
    amount_b: float,
    tolerance: float,
) -> bool:

    denominator = max(
        abs(amount_a),
        abs(amount_b),
        1e-9,
    )

    return (
        abs(amount_a - amount_b) / denominator
        <= tolerance
    )


def transaction_time_proximity(
    times_a: list,
    times_b: list,
    window_hours: float,
) -> bool:

    if not times_a or not times_b:
        return False

    a = sorted(times_a)
    b = sorted(times_b)

    j = 0

    for time_a in a:

        while (
            j < len(b)
            and b[j] < time_a
        ):
            j += 1

        candidates = []

        if j < len(b):
            candidates.append(b[j])

        if j > 0:
            candidates.append(b[j - 1])

        for time_b in candidates:

            difference_hours = abs(
                (time_a - time_b).total_seconds()
            ) / 3600.0

            if difference_hours <= window_hours:
                return True

    return False


# ============================================================================
# OBSERVABLE RELATIONSHIP INDEX
# ============================================================================


def build_relationship_index(data: RawData):
    """
    Build customer/device/network relationships directly from
    the RawData DataFrames.

    Ground truth is intentionally absent.
    """

    customer_devices: dict[str, set[str]] = {}
    customer_networks: dict[str, set[str]] = {}

    device_customers: dict[str, set[str]] = {}
    network_customers: dict[str, set[str]] = {}

    transaction_times: dict[str, list] = {}
    transaction_amounts: dict[str, list[float]] = {}

    # ------------------------------------------------------------------
    # Customer -> Device
    # ------------------------------------------------------------------

    for row in data.device_links.itertuples(index=False):

        customer_id = str(row.customer_id)
        device_id = str(row.device_id)

        customer_devices.setdefault(
            customer_id,
            set(),
        ).add(device_id)

        device_customers.setdefault(
            device_id,
            set(),
        ).add(customer_id)

    # ------------------------------------------------------------------
    # Customer -> Network
    # ------------------------------------------------------------------

    for row in data.network_links.itertuples(index=False):

        customer_id = str(row.customer_id)
        network_id = str(row.network_id)

        customer_networks.setdefault(
            customer_id,
            set(),
        ).add(network_id)

        network_customers.setdefault(
            network_id,
            set(),
        ).add(customer_id)

    # ------------------------------------------------------------------
    # Customer transaction behavior
    # ------------------------------------------------------------------

    for row in data.transactions.itertuples(index=False):

        customer_id = str(row.customer_id)

        created_at = row.created_at

        if created_at is not None:
            transaction_times.setdefault(
                customer_id,
                [],
            ).append(created_at)

        transaction_amounts.setdefault(
            customer_id,
            [],
        ).append(
            safe_float(row.amount)
        )

    return (
        customer_devices,
        customer_networks,
        device_customers,
        network_customers,
        transaction_times,
        transaction_amounts,
    )


# ============================================================================
# COMPONENT MAP
# ============================================================================


def build_component_map(
    m2_results: list[dict],
) -> dict[str, str]:

    """
    Map each customer to its M2 connected-component candidate.

    M2 already performs transitive graph clustering, so this tells us
    whether a 2-hop relationship is genuinely crossing candidate
    components or merely adding evidence inside an existing component.
    """

    result: dict[str, str] = {}

    for cluster in m2_results:

        cluster_id = str(
            cluster["cluster_id"]
        )

        for customer_id in cluster["customers"]:

            result[str(customer_id)] = cluster_id

    return result


# ============================================================================
# 2-HOP GENERATION
# ============================================================================


def generate_raw_two_hop_pairs(
    device_customers: dict[str, set[str]],
    network_customers: dict[str, set[str]],
):
    """
    Generate:

        Customer A -> shared intermediary -> Customer B

    where intermediary is a Device or Network.

    Returns one entry per unique customer pair.
    """

    pair_devices: dict[tuple[str, str], set[str]] = {}
    pair_networks: dict[tuple[str, str], set[str]] = {}

    # ---------------------------------------------------------------
    # Device-mediated relationships
    # ---------------------------------------------------------------

    for device_id, customers in device_customers.items():

        customers = sorted(customers)

        for i in range(len(customers)):

            for j in range(i + 1, len(customers)):

                pair = (
                    customers[i],
                    customers[j],
                )

                pair_devices.setdefault(
                    pair,
                    set(),
                ).add(device_id)

    # ---------------------------------------------------------------
    # Network-mediated relationships
    # ---------------------------------------------------------------

    for network_id, customers in network_customers.items():

        customers = sorted(customers)

        for i in range(len(customers)):

            for j in range(i + 1, len(customers)):

                pair = (
                    customers[i],
                    customers[j],
                )

                pair_networks.setdefault(
                    pair,
                    set(),
                ).add(network_id)

    # ---------------------------------------------------------------
    # Merge
    # ---------------------------------------------------------------

    all_pairs = (
        set(pair_devices)
        | set(pair_networks)
    )

    results = []

    for customer_a, customer_b in sorted(all_pairs):

        devices = pair_devices.get(
            (customer_a, customer_b),
            set(),
        )

        networks = pair_networks.get(
            (customer_a, customer_b),
            set(),
        )

        intermediary_degrees = []

        for device_id in devices:

            intermediary_degrees.append(
                len(
                    device_customers[
                        device_id
                    ]
                )
            )

        for network_id in networks:

            intermediary_degrees.append(
                len(
                    network_customers[
                        network_id
                    ]
                )
            )

        max_degree = (
            max(intermediary_degrees)
            if intermediary_degrees
            else 0
        )

        results.append(
            {
                "customer_a": customer_a,
                "customer_b": customer_b,
                "shared_devices": len(devices),
                "shared_networks": len(networks),
                "max_degree": max_degree,
            }
        )

    return results


# ============================================================================
# 2-HOP FILTERING
# ============================================================================


def filter_two_hop_pairs(
    raw_pairs,
    component_map,
    transaction_times,
    transaction_amounts,
):

    degree_filtered = []

    for pair in raw_pairs:

        if (
            pair["max_degree"]
            <= MAX_INTERMEDIARY_DEGREE
        ):

            degree_filtered.append(pair)

    temporal_filtered = []

    for pair in degree_filtered:

        customer_a = pair["customer_a"]
        customer_b = pair["customer_b"]

        close_48h = transaction_time_proximity(
            transaction_times.get(
                customer_a,
                [],
            ),
            transaction_times.get(
                customer_b,
                [],
            ),
            TEMPORAL_WINDOW_HOURS,
        )

        if close_48h:

            temporal_filtered.append(
                pair
            )

    behavior_filtered = []

    for pair in temporal_filtered:

        customer_a = pair["customer_a"]
        customer_b = pair["customer_b"]

        close_24h = transaction_time_proximity(
            transaction_times.get(
                customer_a,
                [],
            ),
            transaction_times.get(
                customer_b,
                [],
            ),
            BEHAVIOR_WINDOW_HOURS,
        )

        similar_amount = False

        amounts_a = transaction_amounts.get(
            customer_a,
            [],
        )

        amounts_b = transaction_amounts.get(
            customer_b,
            [],
        )

        for amount_a in amounts_a:

            for amount_b in amounts_b:

                if amounts_similar(
                    amount_a,
                    amount_b,
                    EXPERIMENT_AMOUNT_TOLERANCE,
                ):

                    similar_amount = True
                    break

            if similar_amount:
                break

        behavioral_signal_count = (
            int(close_24h)
            + int(similar_amount)
        )

        if (
            behavioral_signal_count
            >= MIN_BEHAVIORAL_SIGNALS
        ):

            enriched = dict(pair)

            enriched[
                "transaction_proximity"
            ] = close_24h

            enriched[
                "amount_similarity"
            ] = similar_amount

            enriched[
                "component_a"
            ] = component_map.get(
                customer_a
            )

            enriched[
                "component_b"
            ] = component_map.get(
                customer_b
            )

            behavior_filtered.append(
                enriched
            )

    return (
        degree_filtered,
        temporal_filtered,
        behavior_filtered,
    )


# ============================================================================
# METRICS
# ============================================================================


def binary_metrics(
    predictions: Iterable[bool],
    labels: Iterable[bool],
):

    predictions = list(predictions)
    labels = list(labels)

    tp = sum(
        p and y
        for p, y in zip(
            predictions,
            labels,
        )
    )

    fp = sum(
        p and not y
        for p, y in zip(
            predictions,
            labels,
        )
    )

    tn = sum(
        not p and not y
        for p, y in zip(
            predictions,
            labels,
        )
    )

    fn = sum(
        not p and y
        for p, y in zip(
            predictions,
            labels,
        )
    )

    precision = (
        tp / (tp + fp)
        if tp + fp
        else 0.0
    )

    recall = (
        tp / (tp + fn)
        if tp + fn
        else 0.0
    )

    f1 = (
        2 * precision * recall
        / (precision + recall)
        if precision + recall
        else 0.0
    )

    fpr = (
        fp / (fp + tn)
        if fp + tn
        else 0.0
    )

    return (
        precision,
        recall,
        f1,
        fpr,
    )


# ============================================================================
# V1 EVALUATION
# ============================================================================


def evaluate_v1(
    scored_clusters,
    ground_truth,
    risk_config,
):

    predictions = []
    labels = []

    for cluster in scored_clusters:

        label = cluster_ground_truth_label(
            cluster,
            ground_truth,
            risk_config,
        )

        if label is None:
            continue

        prediction = (
            cluster.risk.score
            >= DETECTOR_THRESHOLD
        )

        predictions.append(
            prediction
        )

        labels.append(label)

    metrics = binary_metrics(
        predictions,
        labels,
    )

    return (
        metrics,
        labels,
    )


# ============================================================================
# 2-HOP GROUND-TRUTH ANALYSIS
# ============================================================================


def analyze_labels(
    pairs,
    ground_truth,
):

    abuse_pairs = 0
    legitimate_pairs = 0
    mixed_pairs = 0

    abuse_customers = set()
    legitimate_customers = set()

    for pair in pairs:

        label_a = ground_truth.get(
            pair["customer_a"]
        )

        label_b = ground_truth.get(
            pair["customer_b"]
        )

        if (
            label_a is None
            or label_b is None
        ):
            continue

        if label_a and label_b:

            abuse_pairs += 1

        elif not label_a and not label_b:

            legitimate_pairs += 1

        else:

            mixed_pairs += 1

        if label_a:
            abuse_customers.add(
                pair["customer_a"]
            )
        else:
            legitimate_customers.add(
                pair["customer_a"]
            )

        if label_b:
            abuse_customers.add(
                pair["customer_b"]
            )
        else:
            legitimate_customers.add(
                pair["customer_b"]
            )

    return (
        abuse_pairs,
        legitimate_pairs,
        mixed_pairs,
        abuse_customers,
        legitimate_customers,
    )


# ============================================================================
# SEED
# ============================================================================


async def collect_seed(
    seed: int,
    split: str,
    session_factory,
) -> SeedResult:

    print()
    print("=" * 72)
    print(f"COLLECTING SEED {seed}")
    print("=" * 72)

    seed_dir = (
        EXPERIMENT_DATA
        / f"seed_{seed}"
    )

    generate_seed(
        seed,
        seed_dir,
    )

    load_seed(
        seed_dir
    )

    async with session_factory() as session:

        print()
        print("Running M2 + M3 pipeline...")

        # ------------------------------------------------------------
        # Observable data
        # ------------------------------------------------------------

        data = await load_raw_data(
            session
        )

        intelligence_config = (
            IntelligenceConfig()
        )

        risk_config = RiskConfig()

        # ------------------------------------------------------------
        # M2
        # ------------------------------------------------------------

        m2_results = run_pipeline(
            data,
            intelligence_config,
        )

        # ------------------------------------------------------------
        # M3
        # ------------------------------------------------------------

        scored_clusters = score_clusters(
            m2_results,
            data,
            risk_config,
        )

        # ------------------------------------------------------------
        # Evaluation-only ground truth
        # ------------------------------------------------------------

        ground_truth = (
            await load_ground_truth(
                session
            )
        )

        print(
            f"Candidate clusters: "
            f"{len(scored_clusters)}"
        )

        print(
            "Ground-truth customers: "
            f"{len(ground_truth)} "
            f"(abuse="
            f"{sum(ground_truth.values())}, "
            f"legitimate="
            f"{len(ground_truth) - sum(ground_truth.values())})"
        )

        # ------------------------------------------------------------
        # V1
        # ------------------------------------------------------------

        (
            v1_metrics,
            labels,
        ) = evaluate_v1(
            scored_clusters,
            ground_truth,
            risk_config,
        )

        (
            v1_precision,
            v1_recall,
            v1_f1,
            v1_fpr,
        ) = v1_metrics

        # ------------------------------------------------------------
        # Observable 2-hop index
        # ------------------------------------------------------------

        (
            _customer_devices,
            _customer_networks,
            device_customers,
            network_customers,
            transaction_times,
            transaction_amounts,
        ) = build_relationship_index(
            data
        )

        # ------------------------------------------------------------
        # Existing M2 components
        # ------------------------------------------------------------

        component_map = (
            build_component_map(
                m2_results
            )
        )

        # ------------------------------------------------------------
        # 2-hop
        # ------------------------------------------------------------

        raw_pairs = (
            generate_raw_two_hop_pairs(
                device_customers,
                network_customers,
            )
        )

        (
            degree_filtered,
            temporal_filtered,
            behavior_filtered,
        ) = filter_two_hop_pairs(
            raw_pairs,
            component_map,
            transaction_times,
            transaction_amounts,
        )

        same_component = sum(
            pair["component_a"]
            is not None
            and pair["component_a"]
            == pair["component_b"]
            for pair in behavior_filtered
        )

        cross_component = sum(
            pair["component_a"]
            is not None
            and pair["component_b"]
            is not None
            and pair["component_a"]
            != pair["component_b"]
            for pair in behavior_filtered
        )

        # ------------------------------------------------------------
        # 2-hop label analysis
        # ------------------------------------------------------------

        (
            abuse_pairs,
            legitimate_pairs,
            mixed_pairs,
            abuse_customers,
            legitimate_customers,
        ) = analyze_labels(
            behavior_filtered,
            ground_truth,
        )

        total_abuse_customers = sum(
            ground_truth.values()
        )

        abuse_coverage = (
            len(abuse_customers)
            / total_abuse_customers
            if total_abuse_customers
            else 0.0
        )

        unique_customers = {
            customer
            for pair in behavior_filtered
            for customer in (
                pair["customer_a"],
                pair["customer_b"],
            )
        }

        # ------------------------------------------------------------
        # Console
        # ------------------------------------------------------------

        print()
        print("2-HOP FILTERING")
        print(
            f"Raw 2-hop pairs       : "
            f"{len(raw_pairs)}"
        )
        print(
            f"After degree filter   : "
            f"{len(degree_filtered)}"
        )
        print(
            f"After temporal filter : "
            f"{len(temporal_filtered)}"
        )
        print(
            f"After behavior filter : "
            f"{len(behavior_filtered)}"
        )
        print(
            f"Cross-component       : "
            f"{cross_component}"
        )
        print(
            f"Same-component        : "
            f"{same_component}"
        )

        print()
        print("V1 M3 DETECTOR")
        print(
            f"Precision             : "
            f"{v1_precision:.4f}"
        )
        print(
            f"Recall                : "
            f"{v1_recall:.4f}"
        )
        print(
            f"F1                    : "
            f"{v1_f1:.4f}"
        )
        print(
            f"FPR                   : "
            f"{v1_fpr:.4f}"
        )

        print()
        print("2-HOP LABEL COVERAGE")
        print(
            f"Abuse customers represented : "
            f"{len(abuse_customers)}/"
            f"{total_abuse_customers} "
            f"({abuse_coverage:.4f})"
        )

        return SeedResult(
            seed=seed,
            split=split,
            candidate_clusters=len(
                scored_clusters
            ),
            labelled_clusters=len(
                labels
            ),
            positive_clusters=sum(
                labels
            ),
            negative_clusters=(
                len(labels)
                - sum(labels)
            ),
            v1_precision=v1_precision,
            v1_recall=v1_recall,
            v1_f1=v1_f1,
            v1_fpr=v1_fpr,
            raw_two_hop_pairs=len(
                raw_pairs
            ),
            degree_filtered_pairs=len(
                degree_filtered
            ),
            temporal_filtered_pairs=len(
                temporal_filtered
            ),
            behavior_filtered_pairs=len(
                behavior_filtered
            ),
            same_component_pairs=same_component,
            cross_component_pairs=cross_component,
            unique_customers=len(
                unique_customers
            ),
            abuse_customers=len(
                abuse_customers
            ),
            legitimate_customers=len(
                legitimate_customers
            ),
            abuse_pairs=abuse_pairs,
            legitimate_pairs=legitimate_pairs,
            mixed_pairs=mixed_pairs,
            abuse_customer_coverage=abuse_coverage,
        )


# ============================================================================
# OUTPUT
# ============================================================================


def write_csv(
    results: list[SeedResult],
) -> None:

    ARTIFACT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    fields = [
        field
        for field in SeedResult.__dataclass_fields__
    ]

    with RESULTS_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        for result in results:

            writer.writerow(
                {
                    field: getattr(
                        result,
                        field,
                    )
                    for field in fields
                }
            )


def mean(values):
    return (
        sum(values) / len(values)
        if values
        else 0.0
    )


def write_report(
    results: list[SeedResult],
) -> None:

    ARTIFACT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    development = [
        r for r in results
        if r.split == "development"
    ]

    held_out = [
        r for r in results
        if r.split == "held_out"
    ]

    total_behavior_pairs = sum(
        r.behavior_filtered_pairs
        for r in results
    )

    total_cross_component = sum(
        r.cross_component_pairs
        for r in results
    )

    cross_component_rate = (
        total_cross_component
        / total_behavior_pairs
        if total_behavior_pairs
        else 0.0
    )

    lines = []

    lines.append(
        "# TrustGraph — 2-Hop Graph Experiment"
    )

    lines.append("")

    lines.append(
        "> LAB-only experiment. "
        "The production TrustGraph detector "
        "was not modified."
    )

    lines.append("")

    lines.append("## Objective")
    lines.append("")

    lines.append(
        "Evaluate whether degree-aware, temporally "
        "filtered and behaviorally corroborated "
        "2-hop customer relationships add useful "
        "information beyond TrustGraph's existing "
        "1-hop Customer ↔ Device ↔ Network "
        "connected-component candidate generation."
    )

    lines.append("")

    lines.append("## Configuration")
    lines.append("")

    lines.append(
        f"- Development seeds: {DEVELOPMENT_SEEDS}"
    )
    lines.append(
        f"- Held-out seeds: {HELD_OUT_SEEDS}"
    )
    lines.append(
        f"- Detector threshold: "
        f"{DETECTOR_THRESHOLD:.1f}"
    )
    lines.append(
        f"- Maximum intermediary degree: "
        f"{MAX_INTERMEDIARY_DEGREE}"
    )
    lines.append(
        f"- Temporal window: "
        f"{TEMPORAL_WINDOW_HOURS:.1f} hours"
    )
    lines.append(
        f"- Behavioral window: "
        f"{BEHAVIOR_WINDOW_HOURS:.1f} hours"
    )
    lines.append(
        f"- Experimental amount tolerance: "
        f"{EXPERIMENT_AMOUNT_TOLERANCE:.2%}"
    )

    lines.append("")

    lines.append("## Data Boundary")
    lines.append("")

    lines.append(
        "2-hop relationships are constructed exclusively "
        "from observable customer/device/network links "
        "and transaction behavior. Ground truth is loaded "
        "only after M2 and M3 processing and is used "
        "exclusively for evaluation."
    )

    lines.append("")

    lines.append("## Per-Seed Results")
    lines.append("")

    lines.append(
        "| Seed | Split | Candidates | Raw 2-Hop | "
        "Degree | Temporal | Behavioral | "
        "Same Component | Cross Component | "
        "V1 Precision | V1 Recall | V1 F1 | V1 FPR |"
    )

    lines.append(
        "|---:|---|---:|---:|---:|---:|---:|"
        "---:|---:|---:|---:|---:|---:|"
    )

    for r in results:

        lines.append(
            f"| {r.seed} | "
            f"{r.split} | "
            f"{r.candidate_clusters} | "
            f"{r.raw_two_hop_pairs} | "
            f"{r.degree_filtered_pairs} | "
            f"{r.temporal_filtered_pairs} | "
            f"{r.behavior_filtered_pairs} | "
            f"{r.same_component_pairs} | "
            f"{r.cross_component_pairs} | "
            f"{r.v1_precision:.4f} | "
            f"{r.v1_recall:.4f} | "
            f"{r.v1_f1:.4f} | "
            f"{r.v1_fpr:.4f} |"
        )

    lines.append("")

    lines.append("## Held-Out V1 Baseline")
    lines.append("")

    lines.append(
        f"- Precision: "
        f"**{mean([r.v1_precision for r in held_out]):.4f}**"
    )

    lines.append(
        f"- Recall: "
        f"**{mean([r.v1_recall for r in held_out]):.4f}**"
    )

    lines.append(
        f"- F1: "
        f"**{mean([r.v1_f1 for r in held_out]):.4f}**"
    )

    lines.append(
        f"- FPR: "
        f"**{mean([r.v1_fpr for r in held_out]):.4f}**"
    )

    lines.append("")

    lines.append("## 2-Hop Summary")
    lines.append("")

    lines.append(
        f"- Total filtered 2-hop pairs: "
        f"**{total_behavior_pairs}**"
    )

    lines.append(
        f"- Total cross-component pairs: "
        f"**{total_cross_component}**"
    )

    lines.append(
        f"- Cross-component rate: "
        f"**{cross_component_rate:.4%}**"
    )

    lines.append(
        f"- Mean held-out abuse-customer coverage: "
        f"**{mean([r.abuse_customer_coverage for r in held_out]):.4f}**"
    )

    lines.append("")

    lines.append("## Interpretation")
    lines.append("")

    if total_cross_component == 0:

        lines.append(
            "No filtered 2-hop relationship crossed an "
            "existing M2 connected component across the "
            "tested seeds."
        )

        lines.append("")

        lines.append(
            "This indicates that the existing transitive "
            "Customer ↔ Device ↔ Network graph already "
            "captures the tested 2-hop relationships "
            "as candidate components."
        )

        lines.append("")

        lines.append(
            "Therefore, simply adding a second-hop traversal "
            "would not provide additional candidate-component "
            "coverage under the tested constraints."
        )

    else:

        lines.append(
            "Filtered 2-hop relationships crossed existing "
            "M2 connected components."
        )

        lines.append("")

        lines.append(
            "This indicates that 2-hop behavioral relationships "
            "may provide information beyond the current "
            "candidate-generation boundary and should be "
            "evaluated as a secondary candidate or validation "
            "mechanism."
        )

    lines.append("")

    lines.append("## Decision Rule")
    lines.append("")

    lines.append(
        "2-hop reasoning should only be integrated into "
        "TrustGraph if a subsequent held-out ablation "
        "demonstrates measurable detection improvement "
        "without unacceptable candidate explosion or "
        "false-positive growth."
    )

    lines.append("")

    lines.append("## Limitation")
    lines.append("")

    lines.append(
        "This experiment evaluates relationship coverage "
        "and corroboration. It does not by itself establish "
        "that 2-hop reasoning improves production precision, "
        "recall or financial outcomes."
    )

    lines.append("")

    REPORT_MD.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


# ============================================================================
# MAIN
# ============================================================================


async def main():

    print("=" * 72)
    print("TRUSTGRAPH — 2-HOP GRAPH EXPERIMENT")
    print("=" * 72)

    print()
    print(
        f"Development seeds : "
        f"{DEVELOPMENT_SEEDS}"
    )

    print(
        f"Held-out seeds    : "
        f"{HELD_OUT_SEEDS}"
    )

    print(
        f"Max degree        : "
        f"{MAX_INTERMEDIARY_DEGREE}"
    )

    print(
        f"Time window       : "
        f"{TEMPORAL_WINDOW_HOURS:.1f} hours"
    )

    print(
        f"Amount tolerance  : "
        f"{EXPERIMENT_AMOUNT_TOLERANCE:.2%}"
    )

    print(
        f"Behavior required : "
        f"{MIN_BEHAVIORAL_SIGNALS}"
    )

    ARTIFACT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    EXPERIMENT_DATA.mkdir(
        parents=True,
        exist_ok=True,
    )

    engine = create_engine()

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    results = []

    try:

        for seed in DEVELOPMENT_SEEDS:

            results.append(
                await collect_seed(
                    seed,
                    "development",
                    session_factory,
                )
            )

            await engine.dispose()

        for seed in HELD_OUT_SEEDS:

            results.append(
                await collect_seed(
                    seed,
                    "held_out",
                    session_factory,
                )
            )

            await engine.dispose()

        write_csv(results)
        write_report(results)

        print()
        print("=" * 72)
        print("2-HOP EXPERIMENT COMPLETE")
        print("=" * 72)

        print()
        print(
            f"Seeds evaluated : "
            f"{len(results)}"
        )

        print(
            f"CSV             : "
            f"{RESULTS_CSV}"
        )

        print(
            f"Report          : "
            f"{REPORT_MD}"
        )

        total_cross = sum(
            r.cross_component_pairs
            for r in results
        )

        print()
        print("2-HOP SUMMARY")
        print(
            f"Filtered pairs total  : "
            f"{sum(r.behavior_filtered_pairs for r in results)}"
        )

        print(
            f"Cross-component total : "
            f"{total_cross}"
        )

        if total_cross == 0:

            print()
            print(
                "RESULT: filtered 2-hop relationships "
                "remained inside existing M2 components."
            )

        else:

            print()
            print(
                "RESULT: filtered 2-hop relationships "
                "crossed existing M2 components."
            )

    finally:

        await engine.dispose()

        try:
            restore_seed_42()

        except Exception as error:

            print()
            print(
                "WARNING: seed-42 restoration failed:"
            )

            print(error)


if __name__ == "__main__":
    asyncio.run(main())