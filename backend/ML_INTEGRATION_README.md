# TrustGraph — ML Integration (LAB-ML)

## Operational role

The validated Gradient Boosting model is promoted as a **secondary behavioral signal** with two bounded uses:

1. Candidate prioritization for investigator workload.
2. Secondary validation of deterministic M3 risk, with detector/ML disagreement exposed as an uncertainty signal.

It does **not** replace deterministic risk scoring and it does **not** make policy or enforcement decisions.

## Training boundary

`train_ml_model.py` is the only runtime-adjacent script that accesses evaluation labels. Ground truth is used to train the offline artifact only. The runtime package under `app/ml/` never imports `GroundTruth`, `app.risk.evaluation`, Gemini, or policy modules.

The artifact is trained only on development seeds `42–46`. Held-out seeds `9001–9005` remain untouched and are evidence for the role-selection experiment, not training data.

## Model

- GradientBoostingClassifier
- 150 estimators
- learning rate 0.05
- max depth 3
- median imputation
- 30 observable features
- ML operating threshold: 0.37
- deterministic risk threshold remains 52.0

## Files

- `app/ml/features.py` — exact validated feature vector.
- `app/ml/service.py` — fail-safe runtime inference and ranking.
- `scripts/train_ml_model.py` — offline development-seed training.
- `scripts/verify_ml_runtime.py` — canonical seed-42 runtime check.

## Important

Do not train this artifact on held-out seeds. Do not add deterministic risk score, risk level, Gemini output, policy output, or ground truth to the feature vector. Do not make the ML prediction the final enforcement authority.
