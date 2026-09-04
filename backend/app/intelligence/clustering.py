"""Candidate cluster detection.

A connected component in the relationship graph is a group of
customers tied together by shared devices and/or shared network
identifiers (directly, or transitively -- if A and B share a device,
and B and C share an IP, all three land in one component). This is a
CANDIDATE cluster, nothing more: whether it's legitimate shared
infrastructure or coordinated abuse is exactly what the seven signal
families in `signals.py` exist to characterize -- clustering itself
makes no such judgement.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from app.intelligence.config import IntelligenceConfig
from app.intelligence.graph_builder import CUSTOMER, DEVICE, NETWORK


@dataclass
class Cluster:
    cluster_id: str
    customer_ids: list[str]
    device_ids: list[str]
    network_ids: list[str]


def find_candidate_clusters(
    graph: nx.Graph, config: IntelligenceConfig
) -> list[Cluster]:
    """Find connected components with at least `min_cluster_size` customers.

    Isolated customers (no shared device/network with anyone) form
    their own singleton components and are excluded -- there is no
    relationship evidence to evaluate for a customer connected to
    nobody, which is exactly the case M2 is meant to skip (individual
    transaction classification is out of scope; see the project brief).
    """
    raw_clusters: list[tuple[list[str], list[str], list[str]]] = []

    for component in nx.connected_components(graph):
        customer_ids = sorted(
            graph.nodes[n]["entity_id"] for n in component if graph.nodes[n]["type"] == CUSTOMER
        )
        if len(customer_ids) < config.min_cluster_size:
            continue

        device_ids = sorted(
            graph.nodes[n]["entity_id"] for n in component if graph.nodes[n]["type"] == DEVICE
        )
        network_ids = sorted(
            graph.nodes[n]["entity_id"] for n in component if graph.nodes[n]["type"] == NETWORK
        )
        raw_clusters.append((customer_ids, device_ids, network_ids))

    # Sort by customer membership (not graph/component iteration order)
    # so cluster IDs are assigned deterministically regardless of any
    # internal NetworkX ordering detail.
    raw_clusters.sort(key=lambda c: c[0])

    return [
        Cluster(
            cluster_id=f"cc-{idx:04d}",
            customer_ids=customer_ids,
            device_ids=device_ids,
            network_ids=network_ids,
        )
        for idx, (customer_ids, device_ids, network_ids) in enumerate(raw_clusters)
    ]
