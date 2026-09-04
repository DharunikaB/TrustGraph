/**
 * M3 evaluation endpoint (ground-truth backed, synthetic dataset only).
 */
import { apiGet } from "./client";

/** GET /risk/evaluation */
export function getEvaluation() {
  return apiGet("/risk/evaluation");
}
