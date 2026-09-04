# TrustGraph Sensitivity Analysis

LAB-only parameter sensitivity experiment for the TrustGraph payment-abuse detector.

## Objective

Measure how detector behavior changes when the two principal operating parameters are varied independently:

- M3 evaluation threshold
- M2 transaction amount-similarity tolerance

## Evaluation discipline

Development seeds 42–46 are used for configuration understanding. Held-out seeds 9001–9005 are used for untouched robustness validation.

Ground truth is used only by the evaluation layer. It is never supplied to M2 candidate generation or M3 risk scoring.

Each parameter is varied independently while the other parameter remains fixed at the production value.

## Production configuration

- Amount similarity tolerance: **0.50%**
- Evaluation threshold: **52.0**

## Threshold sensitivity — development

| Threshold | Precision | Recall | F1 | FPR | Avg candidates |
|---:|---:|---:|---:|---:|---:|
| 20.0 | 0.4020 | 0.9714 | 0.5666 | 0.5336 | 79.00 |
| 30.0 | 0.4267 | 0.7776 | 0.5477 | 0.3872 | 79.00 |
| 40.0 | 0.3919 | 0.6360 | 0.4811 | 0.3696 | 79.00 |
| 50.0 | 0.8839 | 0.4072 | 0.5503 | 0.0216 | 79.00 |
| 52.0 | 0.9333 | 0.3700 | 0.5248 | 0.0111 | 79.00 |
| 55.0 | 0.9600 | 0.3314 | 0.4864 | 0.0038 | 79.00 |
| 60.0 | 1.0000 | 0.2738 | 0.4194 | 0.0000 | 79.00 |
| 70.0 | 1.0000 | 0.1235 | 0.2167 | 0.0000 | 79.00 |
| 80.0 | 1.0000 | 0.0100 | 0.0952 | 0.0000 | 79.00 |
| 90.0 | n/a | 0.0000 | n/a | 0.0000 | 79.00 |

## Threshold sensitivity — held-out

| Threshold | Precision | Recall | F1 | FPR | Avg candidates |
|---:|---:|---:|---:|---:|---:|
| 20.0 | 0.3581 | 0.9738 | 0.5217 | 0.5818 | 84.60 |
| 30.0 | 0.3975 | 0.8774 | 0.5448 | 0.4437 | 84.60 |
| 40.0 | 0.3493 | 0.6887 | 0.4608 | 0.4273 | 84.60 |
| 50.0 | 0.7450 | 0.4533 | 0.5623 | 0.0509 | 84.60 |
| 52.0 | 0.8892 | 0.4180 | 0.5678 | 0.0185 | 84.60 |
| 55.0 | 0.9444 | 0.3489 | 0.5047 | 0.0089 | 84.60 |
| 60.0 | 1.0000 | 0.2484 | 0.3936 | 0.0000 | 84.60 |
| 70.0 | 1.0000 | 0.1075 | 0.1918 | 0.0000 | 84.60 |
| 80.0 | 1.0000 | 0.0395 | 0.0940 | 0.0000 | 84.60 |
| 90.0 | n/a | 0.0000 | n/a | 0.0000 | 84.60 |

## Amount tolerance sensitivity — development

| Tolerance | Precision | Recall | F1 | FPR | Customer coverage |
|---:|---:|---:|---:|---:|---:|
| 0.10% | 0.9262 | 0.3605 | 0.5134 | 0.0111 | 0.2493 |
| 0.25% | 0.9262 | 0.3605 | 0.5134 | 0.0111 | 0.2493 |
| 0.50% | 0.9333 | 0.3700 | 0.5248 | 0.0111 | 0.2573 |
| 0.75% | 0.9333 | 0.3700 | 0.5248 | 0.0111 | 0.2573 |
| 1.00% | 0.9192 | 0.3700 | 0.5211 | 0.0147 | 0.2573 |

## Amount tolerance sensitivity — held-out

| Tolerance | Precision | Recall | F1 | FPR | Customer coverage |
|---:|---:|---:|---:|---:|---:|
| 0.10% | 0.9492 | 0.4180 | 0.5781 | 0.5781 | 0.2880 |
| 0.25% | 0.9092 | 0.4180 | 0.5710 | 0.5710 | 0.2880 |
| 0.50% | 0.8892 | 0.4180 | 0.5678 | 0.5678 | 0.2880 |
| 0.75% | 0.8771 | 0.4180 | 0.5647 | 0.5647 | 0.2880 |
| 1.00% | 0.8771 | 0.4180 | 0.5647 | 0.5647 | 0.2880 |

## Interpretation

The current operating point of 52 is an evaluation operating point selected from development behavior and subsequently checked against untouched held-out seeds. It is not a universal fraud boundary.

The amount-similarity tolerance is supporting evidence only. Changing this value changes how transaction amount similarity is measured; it does not redefine abuse.

Sensitivity results are robustness evidence on controlled synthetic datasets and must not be interpreted as production fraud-detection performance guarantees.

## Methodology

Each configuration changes one parameter while keeping the other at its production value.

For threshold sensitivity, amount similarity remains fixed at 0.50%.

For amount tolerance sensitivity, the evaluation threshold remains fixed at 52.

Every seed is regenerated and loaded independently before evaluation.

## Reproducibility

- Development seeds: `[42, 43, 44, 45, 46]`
- Held-out seeds: `[9001, 9002, 9003, 9004, 9005]`
- Threshold configurations: `10`
- Amount tolerance configurations: `5`
- Total observations: `150`
- CSV artifact: `C:\Users\dharu\TrustGraph-LAB-ML\backend\artifacts\sensitivity_experiments\sensitivity_multiseed.csv`
