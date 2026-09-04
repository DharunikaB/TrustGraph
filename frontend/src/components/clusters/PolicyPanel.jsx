import { ArrowDown, Scale, Users } from "lucide-react";
import Badge from "../common/Badge";

/**
 * Shows M5's deterministic PolicyDecision, and -- when the AI's
 * recommendation differs from the final decision -- makes that
 * disagreement visually explicit. This is the concrete demonstration
 * that Gemini advises and the deterministic Policy Engine decides.
 */
export default function PolicyPanel({ decision }) {
  if (!decision) {
    return (
      <div className="rounded-lg border border-border bg-panel p-4">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-text">
          <Scale className="h-4 w-4 text-accent" />
          Policy Engine
        </h2>
        <p className="mt-2 text-xs text-text-faint">
          Run "Run Full Response" to evaluate this cluster against TrustGraph's deterministic policy.
        </p>
      </div>
    );
  }

  const disagreement = decision.ai_recommendation && !decision.ai_recommendation_followed;

  return (
    <div className="rounded-lg border border-border bg-panel p-4">
      <h2 className="flex items-center gap-1.5 text-sm font-semibold text-text">
        <Scale className="h-4 w-4 text-accent" />
        Policy Engine
        <span className="ml-auto rounded border border-border-strong px-1.5 py-0.5 text-[10px] font-mono text-text-faint">
          policy {decision.policy_version}
        </span>
      </h2>

      {decision.ai_recommendation && (
        <div className="mt-3 flex flex-col items-center gap-1">
          <div className="w-full rounded border border-border-strong bg-panel-raised px-3 py-2 text-center">
            <div className="text-[10px] uppercase tracking-wide text-text-faint">AI Investigator recommends</div>
            <Badge value={decision.ai_recommendation} kind="action" className="mt-1" />
          </div>
          <ArrowDown className="h-4 w-4 text-text-faint" />
          <div
            className={`w-full rounded border px-3 py-2 text-center ${
              disagreement ? "border-accent/60 bg-accent-soft" : "border-border-strong bg-panel-raised"
            }`}
          >
            <div className="text-[10px] uppercase tracking-wide text-text-faint">Policy Engine decides</div>
            <Badge value={decision.decision} kind="action" className="mt-1" />
            {disagreement && (
              <div className="mt-1.5 text-[11px] font-semibold text-accent">
                AI recommendation overridden — policy retains control
              </div>
            )}
          </div>
        </div>
      )}

      {!decision.ai_recommendation && (
        <div className="mt-3 rounded border border-border-strong bg-panel-raised px-3 py-2 text-center">
          <div className="text-[10px] uppercase tracking-wide text-text-faint">Decision (risk-only baseline)</div>
          <Badge value={decision.decision} kind="action" className="mt-1" />
        </div>
      )}

      <div className="mt-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-faint">Reason Codes</h3>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {decision.reason_codes.map((code) => (
            <span
              key={code}
              className="rounded border border-border-strong bg-panel-raised px-1.5 py-0.5 font-mono text-[10px] text-text-muted"
            >
              {code}
            </span>
          ))}
        </div>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-text-muted">{decision.decision_reason}</p>

      <div className="mt-3 flex items-center gap-1.5 rounded border border-border-strong bg-panel-raised px-3 py-2 text-xs">
        <Users className="h-3.5 w-3.5 shrink-0 text-text-faint" />
        <span className={decision.requires_human_review ? "font-semibold text-orange-400" : "text-text-muted"}>
          {decision.requires_human_review ? "Human review required" : "No human review required"}
        </span>
      </div>
    </div>
  );
}
