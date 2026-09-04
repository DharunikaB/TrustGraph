# TrustGraph — ML Role Experiment

## Purpose

LAB-only evaluation of three possible operational roles for the previously evaluated Gradient Boosting model.

The production TrustGraph pipeline was not modified.

Roles:

1. Risk augmentation
2. Candidate prioritization
3. Secondary validation

Ground truth was obtained exclusively through `app.risk.evaluation` and was never included in the ML feature vector.

## Important Evaluation Note

This experiment uses a controlled 70/30 training/holdout split of the current labelled candidate-cluster population.
It is NOT a replacement for the previously generated multi-seed grouped validation.

The multi-seed validation remains the authoritative evidence for generalization.

## Model

- Model: Gradient Boosting
- Feature count: 30
- ML threshold: 0.37
- Deterministic risk threshold: 52.0
- Random seed: 20260903

## Baseline ML Holdout

- Precision: 1.0000
- Recall: 1.0000
- F1: 1.0000
- FPR: 0.0000
- ROC-AUC: 1.0000
- PR-AUC: 1.0000

## Role A — Risk Augmentation

Experimental formula:

`adjusted_score = deterministic_score + 20 * (ML_probability - 0.5)`

The adjustment is bounded to +/-10 risk points.

- Precision: 1.0000
- Recall: 0.5000
- F1: 0.6667
- FPR: 0.0000

This formula is experimental and is not automatically promoted into the production risk engine.

## Role B — Candidate Prioritization

- Prioritization budget: 25%
- Candidates prioritized: 6
- Precision among prioritized candidates: 0.6667
- Recall among prioritized candidates: 1.0000

This role treats ML as an investigation-ranking layer rather than as the final risk authority.

## Role C — Secondary Validation

- Detector precision: 1.0000
- Detector recall: 0.5000
- Detector F1: 0.6667
- ML precision: 1.0000
- ML recall: 1.0000
- ML F1: 1.0000
- Detector/ML disagreements: 2
- Agreement rate: 0.9167

Disagreement is treated as an uncertainty signal for additional investigation rather than as permission for ML to override deterministic safety controls.

## Interpretation

These results are controlled synthetic-data experiments.
They are not production fraud-detection performance claims.

The final ML role should be selected using:

- held-out performance
- false-positive behavior
- operational usefulness
- robustness under adversarial testing
- compatibility with deterministic safety controls

The existing multi-seed validation and adversarial experiments remain separate evidence artifacts.

## Feature Families

Features are derived from observable graph, infrastructure, account-creation, temporal, transaction, amount, return, and behavioral measurements.

Excluded from features:

- GroundTruth
- deterministic risk score
- risk level
- Gemini output
- policy decision
