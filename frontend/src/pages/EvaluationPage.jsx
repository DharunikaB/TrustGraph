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
    return <LoadingState label="Running evaluation against ground truth..." />;
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

  const cluster = data.cluster_level || {};
  const customer = data.customer_level || {};
  const summary = data.summary || {};

  const productionThreshold = data.evaluation_threshold ?? 52;

  return (
    <div className="space-y-5">
      <div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-bold text-text">
              Detector Evaluation
            </h1>
            <p className="mt-0.5 text-sm text-text-muted">
              Production-facing validation of TrustGraph detection quality.
            </p>
          </div>

          <span className="rounded-full border border-border bg-panel px-2.5 py-1 text-[10px] font-semibold text-text-muted">
            Operating point = {productionThreshold}
          </span>
        </div>

        <p className="mt-2 text-xs text-amber-400">
          Controlled synthetic evaluation. Ground truth is evaluation-only and
          never enters the runtime detection, scoring, policy, or action path.
        </p>
      </div>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="Candidate Clusters"
          value={formatNumber(summary.num_candidate_clusters ?? 0)}
        />
        <MetricCard
          label="Detected Abuse Clusters"
          value={formatNumber(summary.num_detected_abuse_clusters ?? 0)}
        />
        <MetricCard
          label="Legitimate Flagged"
          value={formatNumber(summary.num_legitimate_clusters_flagged ?? 0)}
        />
        <MetricCard
          label="Flagged Transaction Value"
          value={formatCurrency(summary.total_flagged_transaction_value ?? 0)}
        />
      </section>

      <section className="rounded-lg border border-border bg-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text">
              Production Validation
            </h2>
            <p className="mt-0.5 text-[11px] text-text-muted">
              Held-out deterministic performance at the selected operating point.
            </p>
          </div>

          <span className="rounded-full border border-emerald-500/20 bg-emerald-500/5 px-2 py-0.5 text-[9px] font-semibold text-emerald-400">
            HELD-OUT
          </span>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-5">
          <ValidationMetric
            label="Precision"
            value={formatPercent(cluster.precision ?? 0)}
          />
          <ValidationMetric
            label="Recall"
            value={formatPercent(cluster.recall ?? 0)}
          />
          <ValidationMetric
            label="F1"
            value={formatPercent(cluster.f1 ?? 0)}
          />
          <ValidationMetric
            label="False Positive Rate"
            value={formatPercent(cluster.false_positive_rate ?? 0)}
          />
          <ValidationMetric
            label="Threshold"
            value={productionThreshold}
          />
        </div>
      </section>

      <section className="rounded-lg border border-border bg-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text">
              ML Secondary Validation
            </h2>
            <p className="mt-0.5 text-[11px] text-text-muted">
              ML challenges and prioritizes the deterministic detector; it does
              not control policy or actions.
            </p>
          </div>

          <span className="rounded-full border border-border bg-background px-2 py-0.5 text-[9px] font-semibold text-text-muted">
            SECONDARY
          </span>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
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
            value={formatPercent(ML_VALIDATION.f1)}
          />
          <ValidationMetric
            label="ROC-AUC"
            value={formatPercent(ML_VALIDATION.rocAuc)}
          />
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <EvidenceCard
            title="Operational Role"
            rows={[
              ["Model", ML_VALIDATION.model],
              ["Features", ML_VALIDATION.features],
              ["ML threshold", ML_VALIDATION.threshold],
              ["Detector disagreements", ML_VALIDATION.disagreements],
            ]}
          />

          <EvidenceCard
            title="Production Boundary"
            rows={[
              ["Risk authority", "Deterministic engine"],
              ["Policy authority", "Deterministic policy engine"],
              ["ML role", "Secondary validation"],
              ["Candidate count", ML_VALIDATION.candidateCount],
            ]}
          />
        </div>
      </section>

      <section className="rounded-lg border border-border bg-panel p-4">
        <div>
          <h2 className="text-sm font-semibold text-text">
            Customer-Level Cross-Check
          </h2>
          <p className="mt-0.5 text-[11px] text-text-muted">
            Independent view of detection quality at the customer level.
          </p>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-5">
          <ValidationMetric
            label="Precision"
            value={formatPercent(customer.precision ?? 0)}
          />
          <ValidationMetric
            label="Recall"
            value={formatPercent(customer.recall ?? 0)}
          />
          <ValidationMetric
            label="F1"
            value={formatPercent(customer.f1 ?? 0)}
          />
          <ValidationMetric
            label="False Positive Rate"
            value={formatPercent(customer.false_positive_rate ?? 0)}
          />
          <ValidationMetric
            label="Threshold"
            value={productionThreshold}
          />
        </div>
      </section>

      {sweep.length > 0 && (
        <section className="rounded-lg border border-border bg-panel p-4">
          <div>
            <h2 className="text-sm font-semibold text-text">
              Threshold Operating Point
            </h2>
            <p className="mt-0.5 text-[11px] text-text-muted">
              The selected threshold balances detection coverage against false
              positives on the evaluation set.
            </p>
          </div>

          <div className="mt-3 h-52">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sweep}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="threshold"
                  tick={{ fontSize: 10 }}
                  stroke="var(--text-muted)"
                />
                <YAxis
                  tick={{ fontSize: 10 }}
                  stroke="var(--text-muted)"
                />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Line
                  type="monotone"
                  dataKey="precision"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  dot={false}
                  name="Precision"
                />
                <Line
                  type="monotone"
                  dataKey="recall"
                  stroke="var(--success)"
                  strokeWidth={2}
                  dot={false}
                  name="Recall"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <section className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text">
              Production Decision
            </h2>
            <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-text-muted">
              Keep the deterministic detector as the production authority.
              Use ML as secondary validation and candidate prioritization.
              Policy decisions remain deterministic and auditable.
            </p>
          </div>

          <span className="rounded-full border border-emerald-500/20 bg-emerald-500/5 px-2 py-1 text-[9px] font-semibold text-emerald-400">
            DETERMINISTIC AUTHORITY
          </span>
        </div>
      </section>

      <section className="rounded-lg border border-border bg-panel p-4">
        <h2 className="text-sm font-semibold text-text">
          Known Evaluation Limitations
        </h2>

        <div className="mt-3 grid gap-2 md:grid-cols-3">
          <DecisionItem
            title="Synthetic ground truth"
            text="Evaluation labels are controlled artifacts and are not runtime detector inputs."
          />
          <DecisionItem
            title="Candidate generation is a bottleneck"
            text="Missed abuse rings at candidate-generation time remain a primary recall limitation."
          />
          <DecisionItem
            title="Infrastructure rotation"
            text="Rotating shared infrastructure identifiers remains the strongest tested blind spot."
          />
        </div>
      </section>
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

