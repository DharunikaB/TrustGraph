/**
 * M4 endpoint: AI Investigator.
 */
import { apiPost } from "./client";

/** POST /agent/investigate/{cluster_id} -- runs the AI Investigator alone. */
export function investigateCluster(clusterId) {
  return apiPost(`/agent/investigate/${encodeURIComponent(clusterId)}`);
}
