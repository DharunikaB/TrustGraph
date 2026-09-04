/**
 * M5 endpoints: Policy Engine, sandbox actions, audit trail.
 */
import { apiGet, apiPost } from "./client";

/** POST /agent/respond/{cluster_id} -- full investigate -> policy -> action -> audit workflow. */
export function respondToCluster(clusterId) {
  return apiPost(`/agent/respond/${encodeURIComponent(clusterId)}`);
}

/** GET /policy/decisions/{decision_id} */
export function getPolicyDecision(decisionId) {
  return apiGet(`/policy/decisions/${encodeURIComponent(decisionId)}`);
}

/** GET /actions/{action_id} */
export function getAction(actionId) {
  return apiGet(`/actions/${encodeURIComponent(actionId)}`);
}

/** GET /audit/{cluster_id} */
export function getAuditTrail(clusterId) {
  return apiGet(`/audit/${encodeURIComponent(clusterId)}`);
}
