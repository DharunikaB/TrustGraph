"""Test for the M6-support `/intelligence/clusters/{cluster_id}/graph`
endpoint -- exposes M2's existing relationship graph at the edge level
for frontend visualization. Computes no new signals/risk; this test
confirms it returns real, correctly-shaped node/edge data for a known
scenario (not a fabricated/decorative graph).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.db.session import get_session
from app.main import app

from tests.test_intelligence import _legitimate_shared_infra_scenario
from tests.test_workflow import _insert_scenario


@pytest.mark.asyncio
async def test_cluster_graph_endpoint_returns_real_nodes_and_edges(async_session):
    data, customer_ids = _legitimate_shared_infra_scenario()
    await _insert_scenario(async_session, data)

    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.get("/intelligence/clusters/cc-0000/graph")
        assert response.status_code == 200
        body = response.json()

        assert body["cluster_id"] == "cc-0000"
        node_types = {n["type"] for n in body["nodes"]}
        assert node_types == {"customer", "device", "network"}

        customer_node_ids = {n["entity_id"] for n in body["nodes"] if n["type"] == "customer"}
        assert customer_node_ids == set(customer_ids)

        edge_types = {e["type"] for e in body["edges"]}
        assert edge_types == {"USES_DEVICE", "CONNECTED_FROM"}
        # 4 customers x (1 device + 1 network) = 8 edges for this scenario.
        assert len(body["edges"]) == 8
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cluster_graph_endpoint_unknown_cluster_returns_error_not_500(async_session):
    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.get("/intelligence/clusters/does-not-exist/graph")
        # A clean 200-with-error-body (matching this project's existing
        # not-found convention) -- never an unhandled crash.
        assert response.status_code != 500
        assert "error" in response.json()
    finally:
        app.dependency_overrides.clear()
