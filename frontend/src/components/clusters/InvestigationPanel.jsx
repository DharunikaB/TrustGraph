import {
  Search,
  Loader2,
  ShieldQuestion,
  BrainCircuit,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import Badge from "../common/Badge";
import { formatPercent } from "../../lib/format";

/**
 * AI Investigator panel.
 *
 * Gemini investigates the structured TrustGraph evidence while the
 * independent ML behavioral assessment is shown as supporting context.
 *
 * Important:
 * - ML does not replace deterministic TrustGraph risk.
 * - Gemini does not make the final operational decision.
 * - The Policy Engine remains the final decision authority.
 */
export default function InvestigationPanel({
  investigation,
  loading,
  error,
  onInvestigate,
}) {
  return (
    <div className="rounded-lg border border-border bg-panel p-4">
      {/* ---------------------------------------------------------
          Header
      --------------------------------------------------------- */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-text">
            <Search className="h-4 w-4 text-accent" />
            AI Investigator
          </h2>

          <p className="mt-1 text-[11px] text-text-faint">
            Gemini investigates TrustGraph evidence and produces an analyst
            recommendation.
          </p>
        </div>

        <button
          type="button"
          onClick={onInvestigate}
          disabled={loading}
          className="flex items-center gap-1.5 rounded border border-accent/50 bg-accent-soft px-3 py-1.5 text-xs font-semibold text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
        >
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {loading ? "Analyzing cluster evidence…" : "Investigate Cluster"}
        </button>
      </div>

      {/* ---------------------------------------------------------
          Error
      --------------------------------------------------------- */}
      {error && (
        <p className="mt-3 rounded border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-red-300">
          Investigation request failed: {error.message}
        </p>
      )}

      {/* ---------------------------------------------------------
          Empty state
      --------------------------------------------------------- */}
      {!investigation && !loading && !error && (
        <div className="mt-4 rounded border border-border-strong bg-panel-raised p-4">
          <div className="flex items-start gap-3">
            <div className="rounded-md border border-accent/30 bg-accent-soft p-2">
              <Search className="h-4 w-4 text-accent" />
            </div>

            <div>
              <p className="text-xs font-medium text-text">
                Investigation not yet run
              </p>

              <p className="mt-1 text-[11px] leading-relaxed text-text-faint">
                Run the AI Investigator to have Gemini examine the cluster's
                graph, behavioral, temporal, transaction, and risk evidence.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------
          Failed / unavailable investigation
      --------------------------------------------------------- */}
      {investigation && investigation.status !== "COMPLETED" && (
        <div className="mt-4 flex items-start gap-3 rounded border border-border-strong bg-panel-raised px-3 py-3">
          <ShieldQuestion className="mt-0.5 h-4 w-4 shrink-0 text-text-faint" />

          <div className="min-w-0 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-text">
                Investigation status
              </span>

              <Badge value={investigation.status} kind="status" />
            </div>

            <p className="mt-1 text-[11px] leading-relaxed text-text-faint">
              {investigation.metadata?.error ||
                "No AI result available; policy will fall back to the deterministic risk baseline."}
            </p>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------
          Completed investigation
      --------------------------------------------------------- */}
      {investigation && investigation.status === "COMPLETED" && (
        <div className="mt-4 space-y-4">
          {/* -----------------------------------------------------
              Assessment summary
          ----------------------------------------------------- */}
          <div className="rounded-lg border border-border-strong bg-panel-raised p-3">
            <div className="flex flex-wrap items-start gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge value={investigation.assessment.classification} />
                  <Badge
                    value={investigation.assessment.severity}
                    kind="status"
                  />
                </div>

                <p className="mt-2 text-xs leading-relaxed text-text-muted">
                  {investigation.summary}
                </p>
              </div>

              <div className="shrink-0 rounded border border-border px-3 py-2 text-right">
                <p className="text-[10px] uppercase tracking-wide text-text-faint">
                  Gemini confidence
                </p>

                <p className="mt-0.5 text-base font-semibold text-text">
                  {formatPercent(
                    investigation.assessment.confidence,
                    0
                  )}
                </p>
              </div>
            </div>
          </div>

          {/* -----------------------------------------------------
              ML assessment
          ----------------------------------------------------- */}
          <MLAssessmentCard investigation={investigation} />

          {/* -----------------------------------------------------
              Investigation findings
          ----------------------------------------------------- */}
          <div className="grid gap-4 lg:grid-cols-2">
            <EvidenceList
              title="Key Findings"
              items={investigation.key_findings?.map((f) => f.finding)}
            />

            <EvidenceList
              title="Supporting Evidence"
              items={investigation.supporting_evidence}
              tone="positive"
            />

            <EvidenceList
              title="Contradicting Evidence"
              items={investigation.contradicting_evidence}
              tone="negative"
            />

            <EvidenceList
              title="Investigation Recommendations"
              items={investigation.investigation_recommendations}
            />
          </div>

          {/* -----------------------------------------------------
              AI recommendation -> Policy
          ----------------------------------------------------- */}
          <div className="rounded-lg border border-accent/30 bg-accent-soft/30 p-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <BrainCircuit className="h-4 w-4 text-accent" />

                <span className="text-xs font-semibold text-text">
                  Gemini Recommendation
                </span>
              </div>

              <ArrowRight className="h-3.5 w-3.5 text-text-faint" />

              <Badge
                value={investigation.recommended_action}
                kind="action"
              />
            </div>

            <div className="mt-2 border-t border-accent/10 pt-2">
              <p className="text-[11px] leading-relaxed text-text-faint">
                Gemini provides investigative judgment only. The Policy Engine
                below evaluates this recommendation together with deterministic
                risk and safety rules before deciding the operational action.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------
   ML assessment
------------------------------------------------------------------- */

function MLAssessmentCard({ investigation }) {
  const ml = investigation.ml_assessment;

  if (!ml) {
    return (
      <div className="rounded-lg border border-border bg-panel-raised p-3">
        <div className="flex items-center gap-2">
          <BrainCircuit className="h-4 w-4 text-text-faint" />

          <div>
            <p className="text-xs font-semibold text-text">
              Behavioral Model
            </p>

            <p className="text-[10px] text-text-faint">
              No ML assessment was available for this investigation.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const probability = formatPercent(ml.probability, 1);

  return (
    <div
      className={`rounded-lg border p-3 ${
        ml.disagreement
          ? "border-amber-400/30 bg-amber-400/5"
          : "border-emerald-400/20 bg-emerald-400/5"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <div
            className={`rounded-md border p-2 ${
              ml.disagreement
                ? "border-amber-400/20 bg-amber-400/10"
                : "border-emerald-400/20 bg-emerald-400/10"
            }`}
          >
            <BrainCircuit
              className={`h-4 w-4 ${
                ml.disagreement
                  ? "text-amber-400"
                  : "text-emerald-400"
              }`}
            />
          </div>

          <div>
            <p className="text-xs font-semibold text-text">
              Behavioral Model Assessment
            </p>

            <p className="mt-0.5 text-[10px] text-text-faint">
              Independent ML signal supplied to the AI Investigator
            </p>
          </div>
        </div>

        <div className="text-right">
          <p className="text-[10px] uppercase tracking-wide text-text-faint">
            Model score
          </p>

          <p className="text-base font-semibold text-text">
            {probability}
          </p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Metric
          label="ML prediction"
          value={ml.prediction ? "ABUSE" : "NOT ABUSE"}
        />

        <Metric
          label="Deterministic"
          value={
            ml.deterministic_prediction
              ? "ABUSE"
              : "NOT ABUSE"
          }
        />

        <Metric
          label="Signal relationship"
          value={ml.disagreement ? "DISAGREES" : "AGREES"}
          emphasis={ml.disagreement}
        />
      </div>

      <div className="mt-3 flex items-start gap-2 border-t border-border/60 pt-2.5">
        {ml.disagreement ? (
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
        ) : (
          <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
        )}

        <p className="text-[10px] leading-relaxed text-text-faint">
          {ml.disagreement
            ? "The behavioral model and deterministic detector disagree. Gemini is given both signals so it can investigate the disagreement rather than silently treating either signal as ground truth."
            : "The behavioral model and deterministic detector agree on the abuse direction. Gemini receives both signals as independent evidence."}
        </p>
      </div>
    </div>
  );
}

function Metric({ label, value, emphasis = false }) {
  return (
    <div className="rounded border border-border bg-panel px-2.5 py-2">
      <p className="text-[9px] uppercase tracking-wide text-text-faint">
        {label}
      </p>

      <p
        className={`mt-0.5 text-[10px] font-semibold ${
          emphasis ? "text-amber-400" : "text-text"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------
   Evidence lists
------------------------------------------------------------------- */

function EvidenceList({ title, items, tone }) {
  if (!items || items.length === 0) return null;

  const color =
    tone === "positive"
      ? "text-emerald-400"
      : tone === "negative"
        ? "text-amber-400"
        : "text-text-muted";

  return (
    <div className="rounded border border-border bg-panel-raised p-3">
      <h3 className="text-[10px] font-semibold uppercase tracking-wide text-text-faint">
        {title}
      </h3>

      <ul className="mt-2 space-y-1">
        {items.map((item, i) => (
          <li
            key={i}
            className={`flex gap-2 text-[11px] leading-relaxed ${color}`}
          >
            <span className="mt-0.5 shrink-0">•</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}