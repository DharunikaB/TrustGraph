# TrustGraph — Real Gemini Policy Ablation

## Purpose

This experiment measures whether a real Gemini investigation materially influences the downstream deterministic Policy Engine.

The same M2+M3 `ScoredCluster` is evaluated twice:

1. **Baseline:** Gemini intentionally unavailable.
2. **AI path:** Real Gemini investigation supplied to the same Policy Engine.

The Policy Engine remains the final decision authority.

## Experiment Controls

- Environment: LAB only
- Gemini model: `gemini-3.5-flash`
- Random seed: `20260903`
- Sample size: `30`
- M2+M3 pipeline executions: 1
- Ground truth used for sampling: **No**
- Ground truth used by investigation: **No**
- Ground truth used by policy: **No**

## Results

| Metric | Result |
|---|---:|
| Sampled clusters | 30 |
| Completed Gemini investigations | 13 |
| Gemini failures | 17 |
| AI recommendation followed | 6 / 13 (46.2%) |
| AI recommendation overridden | 7 / 13 (53.8%) |
| Policy decisions changed | 1 / 13 (7.7%) |
| Mean Gemini latency | 28363.4 ms |

## Gemini Classifications

```text
{'POTENTIAL_COORDINATED_ABUSE': 6, 'LEGITIMATE_SHARED_INFRASTRUCTURE': 7}
```

## Baseline Policy Decisions

```text
{'ESCALATE': 5, 'NO_ACTION': 12, 'HOLD_FOR_REVIEW': 3, 'MONITOR': 8, 'REVIEW': 2}
```

## Gemini-Aware Policy Decisions

```text
{'ESCALATE': 3, 'NO_ACTION': 6, 'HOLD_FOR_REVIEW': 1, 'REVIEW': 2, 'MONITOR': 1}
```

## Interpretation

This experiment should be interpreted as an ablation of downstream policy influence, not as a fraud-detection accuracy benchmark.

A non-zero decision-change rate demonstrates that the structured Gemini investigation can materially influence Policy Engine outcomes.

A non-zero override rate demonstrates that deterministic policy controls can reject or constrain an AI recommendation.

AI remains advisory and bounded; it does not directly execute actions or override deterministic safety controls.

## Limitations

- The sample is intentionally small because this is a real provider experiment rather than an offline simulation.
- Provider availability and latency can vary.
- Synthetic TrustGraph data is not representative of production payment traffic.
- This experiment does not establish production fraud-detection performance.
- Gemini failures are recorded separately and are not silently converted into successful AI investigations.

## Artifact

Raw experiment data:

`artifacts/gemini_experiments/real_gemini_policy_ablation.csv`
