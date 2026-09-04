/**
 * M2/M3 endpoints: candidate clusters with risk scoring.
 */
import { apiGet } from "./client";

/** GET /risk/clusters?limit=N -- scored clusters, sorted by risk desc. */
export function getRiskClusters(limit = 100) {
  return apiGet(`/risk/clusters?limit=${limit}`);
}

/** GET /risk/clusters/{cluster_id} -- single scored cluster. */
export function getRiskClusterDetail(clusterId) {
  return apiGet(`/risk/clusters/${encodeURIComponent(clusterId)}`);
}

/** GET /intelligence/clusters/{cluster_id}/graph -- raw nodes/edges for React Flow. */
export function getClusterGraph(clusterId) {
  return apiGet(`/intelligence/clusters/${encodeURIComponent(clusterId)}/graph`);
}

/** GET /stats -- row counts, used for the dashboard's dataset summary. */
export function getStats() {
  return apiGet("/stats");
}

/** GET /health, GET /health/db -- backend/database liveness. */
export function getHealth() {
  return apiGet("/health");
}

export function getHealthDb() {
  return apiGet("/health/db");
}
