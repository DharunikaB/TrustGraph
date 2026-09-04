# TrustGraph — 2-Hop Graph Experiment

> LAB-only experiment. The production TrustGraph detector was not modified.

## Objective

Evaluate whether degree-aware, temporally filtered and behaviorally corroborated 2-hop customer relationships add useful information beyond TrustGraph's existing 1-hop Customer ↔ Device ↔ Network connected-component candidate generation.

## Configuration

- Development seeds: [42, 43, 44, 45, 46]
- Held-out seeds: [9001, 9002, 9003, 9004, 9005]
- Detector threshold: 52.0
- Maximum intermediary degree: 8
- Temporal window: 48.0 hours
- Behavioral window: 24.0 hours
- Experimental amount tolerance: 5.00%

## Data Boundary

2-hop relationships are constructed exclusively from observable customer/device/network links and transaction behavior. Ground truth is loaded only after M2 and M3 processing and is used exclusively for evaluation.

## Per-Seed Results

| Seed | Split | Candidates | Raw 2-Hop | Degree | Temporal | Behavioral | Same Component | Cross Component | V1 Precision | V1 Recall | V1 F1 | V1 FPR |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 42 | development | 80 | 506 | 506 | 219 | 182 | 182 | 0 | 1.0000 | 0.2857 | 0.4444 | 0.0000 |
| 43 | development | 78 | 591 | 591 | 284 | 249 | 249 | 0 | 1.0000 | 0.4286 | 0.6000 | 0.0000 |
| 44 | development | 78 | 529 | 529 | 243 | 194 | 194 | 0 | 0.9167 | 0.5000 | 0.6471 | 0.0179 |
| 45 | development | 74 | 524 | 524 | 231 | 194 | 194 | 0 | 0.7500 | 0.2857 | 0.4138 | 0.0377 |
| 46 | development | 85 | 512 | 512 | 184 | 146 | 146 | 0 | 1.0000 | 0.3500 | 0.5185 | 0.0000 |
| 9001 | held_out | 79 | 606 | 606 | 273 | 230 | 230 | 0 | 0.9000 | 0.3750 | 0.5294 | 0.0182 |
| 9002 | held_out | 89 | 496 | 496 | 200 | 156 | 156 | 0 | 0.8000 | 0.3810 | 0.5161 | 0.0294 |
| 9003 | held_out | 94 | 510 | 510 | 198 | 171 | 171 | 0 | 0.8462 | 0.4583 | 0.5946 | 0.0286 |
| 9004 | held_out | 77 | 449 | 449 | 182 | 147 | 147 | 0 | 1.0000 | 0.4667 | 0.6364 | 0.0000 |
| 9005 | held_out | 84 | 560 | 560 | 235 | 189 | 189 | 0 | 0.9000 | 0.4091 | 0.5625 | 0.0161 |

## Held-Out V1 Baseline

- Precision: **0.8892**
- Recall: **0.4180**
- F1: **0.5678**
- FPR: **0.0185**

## 2-Hop Summary

- Total filtered 2-hop pairs: **1858**
- Total cross-component pairs: **0**
- Cross-component rate: **0.0000%**
- Mean held-out abuse-customer coverage: **0.4227**

## Interpretation

No filtered 2-hop relationship crossed an existing M2 connected component across the tested seeds.

This indicates that the existing transitive Customer ↔ Device ↔ Network graph already captures the tested 2-hop relationships as candidate components.

Therefore, simply adding a second-hop traversal would not provide additional candidate-component coverage under the tested constraints.

## Decision Rule

2-hop reasoning should only be integrated into TrustGraph if a subsequent held-out ablation demonstrates measurable detection improvement without unacceptable candidate explosion or false-positive growth.

## Limitation

This experiment evaluates relationship coverage and corroboration. It does not by itself establish that 2-hop reasoning improves production precision, recall or financial outcomes.
