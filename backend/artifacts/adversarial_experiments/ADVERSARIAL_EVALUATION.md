# TrustGraph — Adversarial Evaluation

LAB-only controlled stress test of the existing M2/M3 detector.

## Attack patterns

1. Amount randomization (±2%).
2. Infrastructure rotation (fresh device/network identifiers).
3. High-fanout camouflage (12 legitimate customers attached to abuse infrastructure).
4. Temporal spreading (±12 hours).
5. Low-and-slow coordination (2–8 hour gaps).

## Methodology

- Every attack starts from a fresh in-memory copy of the clean dataset.
- Ground truth is unchanged and used only by the evaluation path.
- M2 candidate generation is unchanged.
- M3 deterministic risk scoring is unchanged.
- Results are controlled synthetic-data stress tests, not production performance.

## Aggregate results

| Split | Attack | Candidates | Precision | Recall | F1 | FPR | Customer Recall |
|---|---|---:|---:|---:|---:|---:|---:|
| development | amount_randomization | 79.0 | 0.9262 | 0.3605 | 0.5134 | 0.0111 | 0.2493 |
| development | baseline | 79.0 | 0.9333 | 0.3700 | 0.5248 | 0.0111 | 0.2573 |
| development | high_fanout_camouflage | 77.4 | 0.9262 | 0.3608 | 0.5143 | 0.0113 | 0.2467 |
| development | infrastructure_rotation | 58.0 | 0.0000 | n/a | n/a | 0.0111 | 0.0000 |
| development | low_and_slow | 79.0 | 0.9357 | 0.3882 | 0.5398 | 0.0111 | 0.2653 |
| development | temporal_spreading | 79.0 | 0.9346 | 0.3791 | 0.5325 | 0.0111 | 0.2613 |
| held_out | amount_randomization | 84.6 | 0.8892 | 0.4180 | 0.5678 | 0.0185 | 0.2880 |
| held_out | baseline | 84.6 | 0.8892 | 0.4180 | 0.5678 | 0.0185 | 0.2880 |
| held_out | high_fanout_camouflage | 82.0 | 0.8848 | 0.4190 | 0.5680 | 0.0191 | 0.2827 |
| held_out | infrastructure_rotation | 63.4 | 0.0000 | n/a | n/a | 0.0185 | 0.0000 |
| held_out | low_and_slow | 84.6 | 0.8947 | 0.4359 | 0.5855 | 0.0185 | 0.2987 |
| held_out | temporal_spreading | 84.6 | 0.8892 | 0.4180 | 0.5678 | 0.0185 | 0.2880 |

## Promotion rule

No mitigation is promoted solely because it helps one attack. A change must improve held-out behavior without unacceptable false-positive growth, candidate explosion, or instability.