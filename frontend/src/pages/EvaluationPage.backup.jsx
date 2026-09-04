import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

import { getEvaluation } from "../api/evaluation";
import { useApiData } from "../lib/useApi";
import {
  LoadingState,
  ErrorState,
  BackendUnavailableState,
} from "../components/common/States";
import {
  formatPercent,
  formatCurrency,
  formatNumber,
} from "../lib/format";

/*
 * ---------------------------------------------------------------------------
 * TrustGraph Evaluation Evidence
 * ---------------------------------------------------------------------------
 *
 * These are controlled offline validation experiments.
 *
 * They are intentionally kept separate from the live deterministic
 * evaluation API. The experiments do NOT modify the production detector,
 * risk score, policy engine, or action path.
 */

/**
 * Final deterministic multi-seed validation.
 */
const FINAL_VALIDATION = {
  development: {
    seeds: "42–46",
    precision: 0.9333,
    recall: 0.37,
    f1: 0.525,
    fpr: 0.0111,
  },

  heldOut: {
    seeds: "9001–9005",
    precision: 0.8892,
    recall: 0.418,
    f1: 0.568,
    fpr: 0.0185,
  },
};

/**
 * ML multi-seed validation.
 *
 * ML is deliberately presented as secondary validation / candidate
 * prioritization rather than as the policy authority.
 */
const ML_VALIDATION = {
  trainingSeeds: "42–46",
  trainingRows: 395,
  positiveRows: 105,
  negativeRows: 290,
  heldOutRows: 423,

  precision: 0.9436,
  recall: 0.9488,
  f1: 0.9448,
  fpr: 0.0184,
  rocAuc: 0.9959,
  prAuc: 0.9896,

  disagreements: 15,
  candidateCount: 80,

  model: "GradientBoostingClassifier",
  features: 30,
  threshold: 0.37,
};

/**
 * ML role experiment.
 *
 * These numbers represent the multi-seed held-out comparison used to select
 * the operational role of ML.
 */
const ML_ROLE_EXPERIMENT = {
  roleA: {
    title: "Risk Augmentation",
    description:
      "Use ML probability as an additional risk signal inside the deterministic score.",
    decision:
      "Not selected as the production role because the deterministic risk engine should remain stable and interpretable.",
  },

  roleB: {
    title: "Candidate Prioritization",
    description:
      "Use ML probability to rank candidate clusters for analyst attention.",
    precision: 0.9148,
    recall: 0.9402,
    decision:
      "Useful operational role for prioritizing analyst attention without changing deterministic policy.",
  },

  roleC: {
    title: "Secondary Validation",
    description:
      "Compare ML prediction against deterministic detection and explicitly surface disagreements.",
    agreement: 0.8387,
    decision:
      "Selected production role. ML validates and challenges the detector without overriding deterministic risk or policy.",
  },
};

/**
 * Adversarial evaluation.
 *
 * The exact per-seed experiment results remain in the offline artifact.
 * We surface the tested attack families and the verified findings here
 * rather than manufacturing a single headline score.
 */
const ADVERSARIAL_TESTS = [
  {
    name: "Amount Randomization",
    mutation: "±2% transaction amount variation",
    finding:
      "Generally robust across the tested seeds, with some degradation on individual seeds.",
    status: "ROBUST",
  },
  {
    name: "Infrastructure Rotation",
    mutation: "Rotate shared infrastructure identifiers",
    finding:
      "Strongest identified blind spot. Abuse-customer coverage dropped to zero across the tested seeds.",
    status: "BLIND SPOT",
  },
  {
    name: "High-Fanout Camouflage",
    mutation: "Increase infrastructure fan-out",
    finding:
      "Produced modest degradation by making shared infrastructure less discriminative.",
    status: "MODERATE IMPACT",
  },
  {
    name: "Temporal Spreading",
    mutation: "Spread activity across approximately ±12 hours",
    finding:
      "Generally remained robust and in some seeds improved candidate separation.",
    status: "ROBUST",
  },
  {
    name: "Low-and-Slow",
    mutation: "Introduce 2–8 hour gaps between activity",
    finding:
      "Mixed but generally retained useful detection coverage.",
    status: "MIXED",
  },
];

/**
 * Sensitivity experiment.
 *
 * 10 thresholds × 10 seeds and 5 amount tolerances × 10 seeds.
 * Production configuration was not changed by this experiment.
 */
const SENSITIVITY_ANALYSIS = {
  rows: 150,
  thresholdSeeds: 10,
  thresholdValues: 10,
  toleranceSeeds: 10,
  toleranceValues: 5,
  productionThreshold: 52,
  productionAmountTolerance: "0.5%",
};

/**
 * 2-hop experiment.
 *
 * This was tested and deliberately rejected from production candidate
 * generation because it did not expand cross-component coverage.
 */
const TWO_HOP_EXPERIMENT = {
  maxIntermediaryDegree: 8,
  windowHours: 48,
  amountTolerance: "5%",
  filteredPairs: 1858,
  crossComponentPairs: 0,
  decision: "NOT PROMOTED",
};

export default function EvaluationPage() {
  const evaluation = useApiData(() => getEvaluation(), []);

  if (evaluation.loading && !evaluation.data) {
    return <LoadingState label="Running evaluation against ground truth…" />;
  }

  if (evaluation.isBackendUnavailable) {
    return <BackendUnavailableState onRetry={evaluation.reload} />;
  }

  if (evaluation.error) {
    return (
      <ErrorState
        message={evaluation.error.message}
        onRetry={evaluation.reload}
      />
    );
  }

  const data = evaluation.data;
  const sweep = data.threshold_sweep_cluster_level || [];

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                             */}
      {/* ------------------------------------------------------------------ */}

      <div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-bold text-text">
              Detector Evaluation
            </h1>

            <p className="mt-0.5 text-sm text-text-muted">
              Validation, robustness, ML cross-checks, and production
              operating-point evidence.
            </p>
          </div>

          <span className="rounded-full border border-border bg-panel px-2 py-0.5 text-[10px] font-semibold text-text-muted">
            Operating point ≥ {data.evaluation_threshold}
          </span>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2">
          <p className="text-sm text-amber-400">
            Controlled synthetic evaluation — ground truth is evaluation-only
            and never enters the detection, scoring, policy, or action path.
          </p>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Final deterministic multi-seed validation                           */}
      {/* ------------------------------------------------------------------ */}

      <section className="rounded-lg border border-border bg-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text">
              Final Multi-Seed Validation
            </h2>

            <p className="mt-0.5 text-[11px] text-text-faint">
              Production-code-path validation across fixed development and
              held-out synthetic seeds at the final operating point.
            </p>
          </div>

          <span className="rounded-full border border-border bg-background px-2 py-1 text-[10px] font-mono text-text-muted">
            threshold ≥ {data.evaluation_threshold}
          </span>
        </div>

        <div className="mt-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                Held-out validation
              </div>

              <div className="text-[11px] text-text-faint">
                Seeds {FINAL_VALIDATION.heldOut.seeds}
              </div>
            </div>

            <span className="rounded-full border border-emerald-500/20 bg-emerald-500/5 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
              Generalization check
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <ValidationMetric
              label="Precision"
              value={formatPercent(FINAL_VALIDATION.heldOut.precision)}
            />

            <ValidationMetric
              label="Recall"
              value={formatPercent(FINAL_VALIDATION.heldOut.recall)}
            />

            <ValidationMetric
              label="F1"
              value={FINAL_VALIDATION.heldOut.f1.toFixed(3)}
            />

            <ValidationMetric
              label="False Positive Rate"
              value={formatPercent(FINAL_VALIDATION.heldOut.fpr)}
            />
          </div>
        </div>

        <div className="mt-4 border-t border-border pt-3">
          <div className="mb-2">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
              Development validation
            </div>

            <div className="text-[11px] text-text-faint">
              Seeds {FINAL_VALIDATION.development.seeds}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <CompactValidationMetric
              label="Precision"
              value={formatPercent(FINAL_VALIDATION.development.precision)}
            />

            <CompactValidationMetric
              label="Recall"
              value={formatPercent(FINAL_VALIDATION.development.recall)}
            />

            <CompactValidationMetric
              label="F1"
              value={FINAL_VALIDATION.development.f1.toFixed(3)}
            />

            <CompactValidationMetric
              label="False Positive Rate"
              value={formatPercent(FINAL_VALIDATION.development.fpr)}
            />
          </div>
        </div>

        <p className="mt-3 text-[10px] leading-relaxed text-text-faint">
          Results are from the controlled synthetic dataset and are not claims
          of production fraud-detection performance.
        </p>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* ML validation                                                      */}
      {/* ------------------------------------------------------------------ */}

      <section className="rounded-lg border border-border bg-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text">
              ML Validation & Secondary Intelligence
            </h2>

            <p className="mt-0.5 text-[11px] text-text-faint">
              Gradient-boosted model trained on engineered graph, temporal,
              transaction, return, and behavioral features. ML does not
              replace deterministic risk or policy.
            </p>
          </div>

          <span className="rounded-full border border-amber-500/20 bg-amber-500/5 px-2 py-1 text-[10px] font-semibold text-amber-400">
            Secondary validation
          </span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <ValidationMetric
            label="Precision"
            value={formatPercent(ML_VALIDATION.precision)}
          />

          <ValidationMetric
            label="Recall"
            value={formatPercent(ML_VALIDATION.recall)}
          />

          <ValidationMetric
            label="F1"
            value={ML_VALIDATION.f1.toFixed(3)}
          />

          <ValidationMetric
            label="False Positive Rate"
            value={formatPercent(ML_VALIDATION.fpr)}
          />

          <ValidationMetric
            label="ROC-AUC"
            value={ML_VALIDATION.rocAuc.toFixed(3)}
          />

          <ValidationMetric
            label="PR-AUC"
            value={ML_VALIDATION.prAuc.toFixed(3)}
          />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
          <EvidenceCard
            title="Model"
            rows={[
              ["Algorithm", ML_VALIDATION.model],
              ["Engineered features", ML_VALIDATION.features],
              ["Training seeds", ML_VALIDATION.trainingSeeds],
              ["Training rows", ML_VALIDATION.trainingRows],
              ["Positive rows", ML_VALIDATION.positiveRows],
              ["Negative rows", ML_VALIDATION.negativeRows],
              ["ML threshold", ML_VALIDATION.threshold],
            ]}
          />

          <EvidenceCard
            title="Operational Role"
            rows={[
              ["Candidate clusters", ML_VALIDATION.candidateCount],
              [
                "Detector / ML disagreements",
                `${ML_VALIDATION.disagreements} / ${ML_VALIDATION.candidateCount}`,
              ],
              ["Production role", "Secondary validation + prioritization"],
              ["Deterministic risk", "Unchanged"],
              ["Ground truth at runtime", "None"],
            ]}
          />

          <div className="rounded-md border border-border bg-background p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
              Why ML is separated
            </div>

            <p className="mt-2 text-[11px] leading-relaxed text-text-faint">
              TrustGraph keeps the deterministic risk engine and policy
              controls authoritative. ML can corroborate a high-risk cluster,
              prioritize investigation, or expose disagreement — but it
              cannot silently rewrite the risk score or authorize an action.
            </p>

            <div className="mt-3 rounded border border-emerald-500/20 bg-emerald-500/5 px-2.5 py-2 text-[10px] text-emerald-300">
              Runtime verification: no ground truth dependency and no
              deterministic-risk mutation.
            </div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* ML role experiment                                                 */}
      {/* ------------------------------------------------------------------ */}

      <section className="rounded-lg border border-border bg-panel p-4">
        <div>
          <h2 className="text-sm font-semibold text-text">
            ML Role Experiment
          </h2>

          <p className="mt-0.5 text-[11px] text-text-faint">
            Three operational roles were evaluated before selecting how ML
            should participate in TrustGraph.
          </p>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
          <RoleCard
            number="A"
            title={ML_ROLE_EXPERIMENT.roleA.title}
            description={ML_ROLE_EXPERIMENT.roleA.description}
            decision={ML_ROLE_EXPERIMENT.roleA.decision}
            status="NOT SELECTED"
          />

          <RoleCard
            number="B"
            title={ML_ROLE_EXPERIMENT.roleB.title}
            description={ML_ROLE_EXPERIMENT.roleB.description}
            decision={ML_ROLE_EXPERIMENT.roleB.decision}
            status="SUPPORTED"
            metrics={[
              ["Top-K precision", formatPercent(ML_ROLE_EXPERIMENT.roleB.precision)],
              ["Top-K recall", formatPercent(ML_ROLE_EXPERIMENT.roleB.recall)],
            ]}
          />

          <RoleCard
            number="C"
            title={ML_ROLE_EXPERIMENT.roleC.title}
            description={ML_ROLE_EXPERIMENT.roleC.description}
            decision={ML_ROLE_EXPERIMENT.roleC.decision}
            status="SELECTED"
            metrics={[
              [
                "Detector / ML agreement",
                formatPercent(ML_ROLE_EXPERIMENT.roleC.agreement),
              ],
            ]}
          />
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Current API evaluation                                             */}
      {/* ------------------------------------------------------------------ */}

      <section className="rounded-lg border border-border bg-panel p-4">
        <div>
          <h2 className="text-sm font-semibold text-text">
            Current Dataset Evaluation
          </h2>

          <p className="mt-0.5 text-[11px] text-text-faint">
            Live evaluation response for the currently loaded synthetic
            dataset at the selected operating point. This reference run uses
            seed 42.
          </p>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCard
            label="Precision"
            value={formatPercent(data.cluster_level.precision)}
          />

          <MetricCard
            label="Recall"
            value={formatPercent(data.cluster_level.recall)}
          />

          <MetricCard
            label="F1"
            value={data.cluster_level.f1?.toFixed(3) ?? "—"}
          />

          <MetricCard
            label="False Positive Rate"
            value={formatPercent(data.cluster_level.false_positive_rate)}
          />
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Customer-level cross-check                                         */}
      {/* ------------------------------------------------------------------ */}

      <section className="rounded-lg border border-border bg-panel p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text">
              Customer-Level Cross-Check
            </h2>

            <p className="mt-0.5 text-[11px] text-text-faint">
              Cluster metrics are the primary operating view; customer metrics
              expose the effect of candidate coverage and isolated accounts.
            </p>
          </div>

          <span className="text-[10px] font-mono text-text-faint">
            same threshold
          </span>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MetricCard
            label="Precision"
            value={formatPercent(data.customer_level.precision)}
          />

          <MetricCard
            label="Recall"
            value={formatPercent(data.customer_level.recall)}
          />

          <MetricCard
            label="F1"
            value={data.customer_level.f1?.toFixed(3) ?? "—"}
          />

          <MetricCard
            label="False Positive Rate"
            value={formatPercent(data.customer_level.false_positive_rate)}
          />
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Threshold trade-off                                                */}
      {/* ------------------------------------------------------------------ */}

      <section className="rounded-lg border border-border bg-panel p-4">
        <h2 className="text-sm font-semibold text-text">
          Threshold Trade-off (Cluster Level)
        </h2>

        <p className="mt-0.5 text-[11px] text-text-faint">
          Raising the risk-score threshold increases precision but reduces
          recall — there is no threshold that maximizes both.
        </p>

        <div className="mt-3">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart
              data={sweep}
              margin={{ top: 12, right: 16, left: -16, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2e38" />

              <XAxis
                dataKey="threshold"
                tick={{ fill: "#9aa1af", fontSize: 11 }}
                axisLine={{ stroke: "#2a2e38" }}
                tickLine={false}
              />

              <YAxis
                domain={[0, 1]}
                tickFormatter={(v) => `${Math.round(v * 100)}%`}
                tick={{ fill: "#9aa1af", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />

              <Tooltip
                contentStyle={{
                  background: "#1d212b",
                  border: "1px solid #2a2e38",
                  borderRadius: 6,
                  fontSize: 12,
                }}
                formatter={(v) =>
                  v === null ? "—" : `${(v * 100).toFixed(1)}%`
                }
              />

              <Legend wrapperStyle={{ fontSize: 11 }} />

              <Line
                type="monotone"
                dataKey="precision"
                name="Precision"
                stroke="#f97316"
                dot={{ r: 3 }}
              />

              <Line
                type="monotone"
                dataKey="recall"
                name="Recall"
                stroke="#38bdf8"
                dot={{ r: 3 }}
              />

              <Line
                type="monotone"
                dataKey="false_positive_rate"
                name="False Positive Rate"
                stroke="#ef4444"
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Sensitivity analysis                                               */}
      {/* ------------------------------------------------------------------ */}

      <section className="rounded-lg border border-border bg-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text">
              Sensitivity Analysis
            </h2>

            <p className="mt-0.5 text-[11px] text-text-faint">
              Threshold and amount-similarity sensitivity were evaluated
              independently to test whether the selected operating point was
              overly dependent on one hardcoded value.
            </p>
          </div>

          <span className="rounded-full border border-border bg-background px-2 py-1 text-[10px] font-mono text-text-muted">
            {SENSITIVITY_ANALYSIS.rows} experiment rows
          </span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <ValidationMetric
            label="Threshold settings"
            value={SENSITIVITY_ANALYSIS.thresholdValues}
          />

          <ValidationMetric
            label="Threshold seeds"
            value={SENSITIVITY_ANALYSIS.thresholdSeeds}
          />

          <ValidationMetric
            label="Amount tolerances"
            value={SENSITIVITY_ANALYSIS.toleranceValues}
          />

          <ValidationMetric
            label="Tolerance seeds"
            value={SENSITIVITY_ANALYSIS.toleranceSeeds}
          />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <EvidenceCard
            title="Threshold Sweep"
            rows={[
              ["Configurations", "10 thresholds × 10 seeds"],
              ["Production threshold", SENSITIVITY_ANALYSIS.productionThreshold],
              ["Purpose", "Precision / recall trade-off"],
              ["Production config changed?", "No"],
            ]}
          />

          <EvidenceCard
            title="Amount Similarity Sweep"
            rows={[
              ["Configurations", "5 tolerances × 10 seeds"],
              ["Production tolerance", SENSITIVITY_ANALYSIS.productionAmountTolerance],
              ["Purpose", "Robustness of amount coordination signal"],
              ["Production config changed?", "No"],
            ]}
          />
        </div>

        <div className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[10px] leading-relaxed text-amber-300">
          The sensitivity experiments are evidence, not a runtime tuning loop.
          The production configuration remains explicitly versioned and
          unchanged by these offline sweeps.
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Adversarial evaluation                                             */}
      {/* ------------------------------------------------------------------ */}

      <section className="rounded-lg border border-border bg-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text">
              Adversarial Robustness
            </h2>

            <p className="mt-0.5 text-[11px] text-text-faint">
              Five controlled attack mutations were used to identify where the
              detector is robust and where an attacker can reduce coverage.
            </p>
          </div>

          <span className="rounded-full border border-red-500/20 bg-red-500/5 px-2 py-1 text-[10px] font-semibold text-red-400">
            Attack-surface analysis
          </span>
        </div>

        <div className="mt-4 space-y-2">
          {ADVERSARIAL_TESTS.map((test) => (
            <AdversarialRow key={test.name} {...test} />
          ))}
        </div>

        <div className="mt-4 rounded-md border border-red-500/20 bg-red-500/5 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-red-300">
            Primary identified blind spot
          </div>

          <p className="mt-1 text-[11px] leading-relaxed text-text-faint">
            Infrastructure rotation was the strongest tested evasion pattern.
            It removes the shared infrastructure signal that the current
            candidate-generation strategy depends on. This limitation is
            documented rather than hidden, and the risky broad 2-hop expansion
            was not promoted simply to compensate for it.
          </p>
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* 2-hop experiment                                                    */}
      {/* ------------------------------------------------------------------ */}

      <section className="rounded-lg border border-border bg-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text">
              2-Hop Graph Expansion Experiment
            </h2>

            <p className="mt-0.5 text-[11px] text-text-faint">
              Degree-capped 2-hop traversal was evaluated as a possible way to
              recover missed abuse rings without introducing unrestricted graph
              expansion.
            </p>
          </div>

          <span className="rounded-full border border-border bg-background px-2 py-1 text-[10px] font-semibold text-text-muted">
            {TWO_HOP_EXPERIMENT.decision}
          </span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <ValidationMetric
            label="Max intermediary degree"
            value={TWO_HOP_EXPERIMENT.maxIntermediaryDegree}
          />

          <ValidationMetric
            label="Time window"
            value={`${TWO_HOP_EXPERIMENT.windowHours}h`}
          />

          <ValidationMetric
            label="Filtered 2-hop pairs"
            value={formatNumber(TWO_HOP_EXPERIMENT.filteredPairs)}
          />

          <ValidationMetric
            label="Cross-component expansions"
            value={TWO_HOP_EXPERIMENT.crossComponentPairs}
          />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <EvidenceCard
            title="Experiment Result"
            rows={[
              ["Amount tolerance", TWO_HOP_EXPERIMENT.amountTolerance],
              ["Filtered candidate pairs", formatNumber(TWO_HOP_EXPERIMENT.filteredPairs)],
              ["Cross-component pairs", TWO_HOP_EXPERIMENT.crossComponentPairs],
              ["Existing components expanded", "No"],
            ]}
          />

          <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-emerald-300">
              Engineering decision
            </div>

            <p className="mt-1 text-[11px] leading-relaxed text-text-faint">
              The experiment did not provide evidence that 2-hop expansion
              improves production candidate coverage. It was therefore
              rejected rather than added for the sake of architectural
              complexity.
            </p>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Summary + financial cost                                           */}
      {/* ------------------------------------------------------------------ */}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-border bg-panel p-4">
          <h2 className="text-sm font-semibold text-text">
            Summary (threshold = {data.evaluation_threshold})
          </h2>

          <dl className="mt-2 space-y-1.5 text-xs">
            <Row
              label="Candidate clusters"
              value={formatNumber(data.summary.num_candidate_clusters)}
            />

            <Row
              label="Detected abuse clusters"
              value={formatNumber(data.summary.num_detected_abuse_clusters)}
            />

            <Row
              label="Legitimate clusters flagged"
              value={formatNumber(
                data.summary.num_legitimate_clusters_flagged
              )}
            />

            <Row
              label="Cluster detection rate"
              value={formatPercent(data.summary.cluster_detection_rate)}
            />

            <Row
              label="Flagged transaction value"
              value={formatCurrency(data.summary.total_flagged_transaction_value)}
            />
          </dl>
        </section>

        <section className="rounded-lg border border-border bg-panel p-4">
          <h2 className="text-sm font-semibold text-text">
            False-Positive Financial Cost
          </h2>

          <dl className="mt-2 space-y-1.5 text-xs">
            <Row
              label="Flagged clusters"
              value={formatNumber(
                data.false_positive_financial_cost.total_flagged_clusters
              )}
            />

            <Row
              label="False positives among them"
              value={formatNumber(
                data.false_positive_financial_cost
                  .false_positive_cluster_count
              )}
            />

            <Row
              label="Associated legitimate transaction value"
              value={formatCurrency(
                data.false_positive_financial_cost
                  .associated_legitimate_transaction_value
              )}
            />
          </dl>

          <p className="mt-2 text-[11px] leading-relaxed text-text-faint">
            {data.false_positive_financial_cost.note}
          </p>
        </section>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Production decision                                                */}
      {/* ------------------------------------------------------------------ */}

      <section className="rounded-lg border border-border bg-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text">
              Production Decision & Known Limits
            </h2>

            <p className="mt-0.5 text-[11px] text-text-faint">
              What the experiments collectively changed — and what they
              deliberately did not change.
            </p>
          </div>

          <span className="rounded-full border border-emerald-500/20 bg-emerald-500/5 px-2 py-1 text-[10px] font-semibold text-emerald-400">
            Evidence-driven configuration
          </span>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <DecisionItem
            title="Deterministic risk remains authoritative"
            text="The final operating point remains threshold 52. ML does not rewrite deterministic risk scores."
          />

          <DecisionItem
            title="ML is secondary intelligence"
            text="ML validates and prioritizes candidates while explicitly exposing detector/ML disagreements."
          />

          <DecisionItem
            title="2-hop expansion was rejected"
            text="The tested degree-capped expansion produced no cross-component coverage improvement."
          />

          <DecisionItem
            title="Infrastructure rotation remains a blind spot"
            text="The adversarial study identified infrastructure rotation as the strongest tested evasion pattern."
          />

          <DecisionItem
            title="Sensitivity did not modify production"
            text="Threshold and amount-tolerance sweeps were kept offline so experimentation could not silently change runtime behavior."
          />

          <DecisionItem
            title="Ground truth stays evaluation-only"
            text="Ground-truth labels are used for controlled validation and training experiments, never as runtime detector input."
          />
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Methodology                                                        */}
      {/* ------------------------------------------------------------------ */}

      {data.methodology_notes?.length > 0 && (
        <section className="rounded-lg border border-border bg-panel p-4">
          <h2 className="text-sm font-semibold text-text">Methodology</h2>

          <ul className="mt-2 space-y-1">
            {data.methodology_notes.map((note, i) => (
              <li
                key={i}
                className="flex gap-1.5 text-[11px] text-text-muted"
              >
                <span className="text-accent">•</span>
                {note}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/* ========================================================================= */
/* Reusable UI pieces                                                       */
/* ========================================================================= */

function ValidationMetric({ label, value }) {
  return (
    <div className="rounded-md border border-border bg-background px-3 py-2.5">
      <div className="text-[10px] text-text-muted">{label}</div>

      <div className="mt-1 text-lg font-bold tabular-nums text-text">
        {value}
      </div>
    </div>
  );
}

function CompactValidationMetric({ label, value }) {
  return (
    <div className="rounded-md border border-border bg-background px-3 py-2">
      <div className="text-[10px] text-text-faint">{label}</div>

      <div className="mt-0.5 text-sm font-semibold tabular-nums text-text">
        {value}
      </div>
    </div>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded-lg border border-border bg-panel px-4 py-3">
      <div className="text-xs text-text-muted">{label}</div>

      <div className="mt-1 text-xl font-bold tabular-nums text-text">
        {value}
      </div>
    </div>
  );
}

function EvidenceCard({ title, rows }) {
  return (
    <div className="rounded-md border border-border bg-background p-3">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
        {title}
      </div>

      <dl className="mt-2 space-y-1.5">
        {rows.map(([label, value]) => (
          <Row key={label} label={label} value={value} />
        ))}
      </dl>
    </div>
  );
}

function RoleCard({
  number,
  title,
  description,
  decision,
  status,
  metrics = [],
}) {
  const selected = status === "SELECTED";

  return (
    <div
      className={`rounded-md border p-3 ${
        selected
          ? "border-emerald-500/30 bg-emerald-500/5"
          : "border-border bg-background"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded border border-border bg-panel text-[10px] font-bold text-text">
            {number}
          </span>

          <div className="text-xs font-semibold text-text">{title}</div>
        </div>

        <span
          className={`rounded-full border px-1.5 py-0.5 text-[9px] font-semibold ${
            selected
              ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400"
              : "border-border text-text-faint"
          }`}
        >
          {status}
        </span>
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-text-faint">
        {description}
      </p>

      {metrics.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          {metrics.map(([label, value]) => (
            <div
              key={label}
              className="rounded border border-border bg-panel px-2 py-1.5"
            >
              <div className="text-[9px] text-text-faint">{label}</div>
              <div className="mt-0.5 text-xs font-semibold text-text">
                {value}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 border-t border-border pt-2 text-[10px] leading-relaxed text-text-muted">
        {decision}
      </div>
    </div>
  );
}

function AdversarialRow({ name, mutation, finding, status }) {
  const blindSpot = status === "BLIND SPOT";

  return (
    <div
      className={`rounded-md border p-3 ${
        blindSpot
          ? "border-red-500/20 bg-red-500/5"
          : "border-border bg-background"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold text-text">{name}</div>

          <div className="mt-0.5 text-[10px] text-text-faint">
            {mutation}
          </div>
        </div>

        <span
          className={`rounded-full border px-1.5 py-0.5 text-[9px] font-semibold ${
            blindSpot
              ? "border-red-500/20 bg-red-500/5 text-red-400"
              : "border-border text-text-muted"
          }`}
        >
          {status}
        </span>
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-text-faint">
        {finding}
      </p>
    </div>
  );
}

function DecisionItem({ title, text }) {
  return (
    <div className="rounded-md border border-border bg-background p-3">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />

        <div>
          <div className="text-[11px] font-semibold text-text">{title}</div>

          <p className="mt-1 text-[10px] leading-relaxed text-text-faint">
            {text}
          </p>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-text-faint">{label}</dt>

      <dd className="text-right font-semibold text-text">{value}</dd>
    </div>
  );
}