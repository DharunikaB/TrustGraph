"""TrustGraph M2 Intelligence Engine pipeline.

    RAW DATA (M1 database)
        |
        v
    GRAPH  (graph_builder.py)
        |
        v
    SIGNALS  (signals.py -- the seven frozen signal families)
        |
        v
    CANDIDATE CLUSTERS  (clustering.py)
        |
        v
    STRUCTURED EVIDENCE  (features.py)

ARCHITECTURAL BOUNDARY -- M2 stops here. This module deliberately does
NOT:

- compute a final risk score or financial exposure (M3)
- call Gemini or implement the AI Investigator (M4)
- implement the Policy Engine, autonomous decisions/actions, or audit
  logging (M5)
- serve a frontend or investigation UI (M6)

`run_pipeline` returns a list of structured evidence dicts (see
`features.build_cluster_evidence`) -- raw, interpretable measurements
plus descriptive (non-judgemental) evidence strings, exactly what M3
needs to consume and nothing more.

GROUND TRUTH SAFETY: this module and everything it imports from
`app.intelligence` never queries the `ground_truth` table and never
imports `GroundTruth`/`GroundTruthLabel`. See `data_loader.py`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.baselines import compute_global_baselines
from app.intelligence.clustering import find_candidate_clusters
from app.intelligence.config import IntelligenceConfig
from app.intelligence.data_loader import RawData, load_raw_data
from app.intelligence.graph_builder import build_relationship_graph
from app.intelligence.features import build_cluster_evidence
from app.intelligence.signals import (
    account_creation_burst_signal,
    graph_connectivity_signal,
    return_anomaly_signal,
    shared_device_signal,
    shared_network_signal,
    transaction_coordination_signal,
    transaction_velocity_signal,
)


def run_pipeline(data: RawData, config: IntelligenceConfig | None = None) -> list[dict]:
    """Run the full M2 pipeline against already-loaded raw data.

    Synchronous and side-effect free -- takes a `RawData` bag in,
    returns a list of structured evidence dicts out. This is what
    tests call directly (constructing `RawData` from a small, known
    scenario) so the pipeline's behavior can be verified without a
    database round-trip.
    """
    config = config or IntelligenceConfig()

    if data.is_empty():
        return []

    relationship_graph = build_relationship_graph(data)
    clusters = find_candidate_clusters(relationship_graph, config)
    if not clusters:
        return []

    baselines = compute_global_baselines(data)

    results = []
    for cluster in clusters:
        cluster_tx_ids = data.transactions[
            data.transactions["customer_id"].isin(cluster.customer_ids)
        ]["id"].tolist()

        signals = {
            "shared_device": shared_device_signal(cluster, data),
            "shared_network": shared_network_signal(cluster, data),
            "account_creation_burst": account_creation_burst_signal(cluster, data, config),
            "transaction_velocity": transaction_velocity_signal(cluster, data, config, baselines),
            "transaction_coordination": transaction_coordination_signal(cluster, data, config),
            "return_anomaly": return_anomaly_signal(cluster, data, config, baselines),
            "graph_connectivity": graph_connectivity_signal(cluster, relationship_graph),
        }

        results.append(
            build_cluster_evidence(
                cluster_id=cluster.cluster_id,
                customer_ids=cluster.customer_ids,
                device_ids=cluster.device_ids,
                network_ids=cluster.network_ids,
                transaction_ids=cluster_tx_ids,
                signals=signals,
                config=config,
            )
        )

    return results


async def run_pipeline_async(
    session: AsyncSession, config: IntelligenceConfig | None = None
) -> list[dict]:
    """Load data from the database and run the pipeline.

    This is the entrypoint used by the FastAPI debug endpoint and by
    `scripts/run_intelligence_pipeline.py`.
    """
    data = await load_raw_data(session)
    return run_pipeline(data, config)
