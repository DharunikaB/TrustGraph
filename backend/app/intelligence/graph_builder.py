"""Builds NetworkX graphs from observable payment/activity data.

Two graphs are built, for two different purposes:

- `build_relationship_graph`: a bipartite customer <-> device/network
  graph used ONLY to find candidate clusters via connected components.
  Kept deliberately small (two edge types) so clustering stays a
  linear-time graph traversal rather than materializing a
  customer-customer clique for every shared device/network -- cliquing
  a device shared by k customers costs O(k^2) edges for no benefit,
  since connected-components membership is all clustering needs.

- `build_full_graph`: the complete heterogeneous graph (customer,
  device, network, transaction, order, return nodes; USES_DEVICE,
  CONNECTED_FROM, MADE_TRANSACTION, HAS_ORDER, RESULTED_IN_RETURN
  edges) intended for later frontend visualization and for any signal
  that needs the transaction/order/return chain, not just clustering.
"""

from __future__ import annotations

import networkx as nx

from app.intelligence.data_loader import RawData

# Node-id prefixes keep the heterogeneous graph's namespace collision-free
# (a customer and a transaction could otherwise share a UUID by pure
# coincidence -- vanishingly unlikely, but free to rule out entirely).
CUSTOMER = "customer"
DEVICE = "device"
NETWORK = "network"
TRANSACTION = "transaction"
ORDER = "order"
RETURN = "return"


def _node_id(node_type: str, entity_id: str) -> str:
    return f"{node_type}:{entity_id}"


def build_relationship_graph(data: RawData) -> nx.Graph:
    """Bipartite customer<->device/network graph, for clustering only."""
    graph = nx.Graph()

    for customer_id in data.customers["id"]:
        graph.add_node(_node_id(CUSTOMER, customer_id), type=CUSTOMER, entity_id=customer_id)

    for device_id in data.devices["id"]:
        graph.add_node(_node_id(DEVICE, device_id), type=DEVICE, entity_id=device_id)

    for network_id in data.networks["id"]:
        graph.add_node(_node_id(NETWORK, network_id), type=NETWORK, entity_id=network_id)

    for _, link in data.device_links.iterrows():
        graph.add_edge(
            _node_id(CUSTOMER, link["customer_id"]),
            _node_id(DEVICE, link["device_id"]),
            type="USES_DEVICE",
            first_seen=link["first_seen"],
            last_seen=link["last_seen"],
        )

    for _, link in data.network_links.iterrows():
        graph.add_edge(
            _node_id(CUSTOMER, link["customer_id"]),
            _node_id(NETWORK, link["network_id"]),
            type="CONNECTED_FROM",
            first_seen=link["first_seen"],
            last_seen=link["last_seen"],
        )

    return graph


def build_full_graph(data: RawData) -> nx.Graph:
    """The complete heterogeneous graph across all six entity types."""
    graph = build_relationship_graph(data)

    for _, tx in data.transactions.iterrows():
        tx_node = _node_id(TRANSACTION, tx["id"])
        graph.add_node(
            tx_node,
            type=TRANSACTION,
            entity_id=tx["id"],
            amount=tx["amount"],
            status=tx["status"],
            created_at=tx["created_at"],
        )
        graph.add_edge(
            _node_id(CUSTOMER, tx["customer_id"]), tx_node, type="MADE_TRANSACTION"
        )

    for _, order in data.orders.iterrows():
        order_node = _node_id(ORDER, order["id"])
        graph.add_node(
            order_node,
            type=ORDER,
            entity_id=order["id"],
            order_amount=order["order_amount"],
            created_at=order["created_at"],
        )
        tx_node = _node_id(TRANSACTION, order["transaction_id"])
        if graph.has_node(tx_node):
            graph.add_edge(tx_node, order_node, type="HAS_ORDER")

    for _, ret in data.returns.iterrows():
        return_node = _node_id(RETURN, ret["id"])
        graph.add_node(
            return_node,
            type=RETURN,
            entity_id=ret["id"],
            amount=ret["amount"],
            reason=ret["reason"],
            created_at=ret["created_at"],
        )
        order_node = _node_id(ORDER, ret["order_id"])
        if graph.has_node(order_node):
            graph.add_edge(order_node, return_node, type="RESULTED_IN_RETURN")

    return graph


def customer_ids_in_component(graph: nx.Graph, component: set[str]) -> list[str]:
    """Extract the customer entity IDs from a connected component of node IDs."""
    return sorted(
        graph.nodes[node]["entity_id"]
        for node in component
        if graph.nodes[node].get("type") == CUSTOMER
    )
