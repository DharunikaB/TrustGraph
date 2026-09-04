# TrustGraph Detector Experiment Report

## Seed generalization (final operating point, cluster level)

|   seed |   candidate_clusters |   abuse_rings |   candidate_ring_coverage |   precision |   recall |     f1 |    fpr |
|-------:|---------------------:|--------------:|--------------------------:|------------:|---------:|-------:|-------:|
|     42 |                   80 |            26 |                    0.8077 |      1      |   0.2857 | 0.4444 | 0      |
|     43 |                   78 |            26 |                    0.8077 |      1      |   0.4286 | 0.6    | 0      |
|     44 |                   78 |            30 |                    0.7333 |      0.9167 |   0.5    | 0.6471 | 0.0179 |
|     45 |                   74 |            28 |                    0.75   |      0.75   |   0.2857 | 0.4138 | 0.0377 |
|     46 |                   85 |            28 |                    0.7143 |      1      |   0.35   | 0.5185 | 0      |
|   9001 |                   79 |            28 |                    0.8571 |      0.9    |   0.375  | 0.5294 | 0.0182 |
|   9002 |                   89 |            27 |                    0.7778 |      0.8    |   0.381  | 0.5162 | 0.0294 |
|   9003 |                   94 |            29 |                    0.8276 |      0.8462 |   0.4583 | 0.5946 | 0.0286 |
|   9004 |                   77 |            27 |                    0.5556 |      1      |   0.4667 | 0.6364 | 0      |
|   9005 |                   84 |            25 |                    0.88   |      0.9    |   0.4091 | 0.5625 | 0.0161 |

## Signal ablation (seed 42, diagnostic threshold 50)

|   seed | variant           |   threshold |   true_positives |   false_positives |   true_negatives |   false_negatives |   precision |   recall |     f1 |   accuracy |   false_positive_rate |
|-------:|:------------------|------------:|-----------------:|------------------:|-----------------:|------------------:|------------:|---------:|-------:|-----------:|----------------------:|
|     42 | baseline          |          50 |                6 |                 0 |               59 |                15 |           1 |   0.2857 | 0.4444 |     0.8125 |                     0 |
|     42 | relationship_zero |          50 |                5 |                 0 |               59 |                16 |           1 |   0.2381 | 0.3846 |     0.8    |                     0 |
|     42 | temporal_zero     |          50 |                2 |                 0 |               59 |                19 |           1 |   0.0952 | 0.1738 |     0.7625 |                     0 |
|     42 | velocity_zero     |          50 |                6 |                 0 |               59 |                15 |           1 |   0.2857 | 0.4444 |     0.8125 |                     0 |
|     42 | coordination_zero |          50 |                6 |                 0 |               59 |                15 |           1 |   0.2857 | 0.4444 |     0.8125 |                     0 |
|     42 | return_zero       |          50 |                6 |                 0 |               59 |                15 |           1 |   0.2857 | 0.4444 |     0.8125 |                     0 |
|     42 | graph_zero        |          50 |                2 |                 0 |               59 |                19 |           1 |   0.0952 | 0.1738 |     0.7625 |                     0 |

## Interpretation

- This harness does not modify production scoring weights.
- Candidate-ring coverage measures a limitation before scoring: abuse rings with no shared device/network relationship are never scored.
- The 9001-9005 seeds are fixed generalization seeds and should be treated as a future held-out set if they are kept untouched during tuning.
- Ablation here is diagnostic: removing a weight changes the score budget, so it is not a causal feature-importance estimate.
## Final decision

The final production detector keeps relationship-first candidate generation.
An experimental secondary behavioral candidate path was tested, but although it
increased candidate coverage, it also created larger/diluted candidates and
reduced headline recall under the existing scoring contract. It was rejected
rather than forced into production.

One narrow improvement was retained: transaction coordination now recognizes
small amount differences using `IntelligenceConfig.amount_similarity_tolerance`
instead of requiring exact amount equality. Broader tolerances were rejected
because they increased false positives disproportionately. The final tolerance
is 0.5%.

The primary evaluation operating point is now score >= 52. This is an evaluation
operating point, not a universal fraud boundary. Risk bands and the deterministic
Policy Engine remain separate from this metric threshold.

Final validation from the production code path:

| Split | Seeds | Precision | Recall | F1 | FPR |
|---|---|---:|---:|---:|---:|
| Development | 42-46 | **93.33%** | 37.00% | 0.525 | 1.11% |
| Held-out | 9001-9005 | **88.92%** | **41.80%** | **0.568** | **1.85%** |

These are synthetic-data results and should be presented as such. They are not
claims of production fraud-detection performance.
