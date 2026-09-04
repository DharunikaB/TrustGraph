import { Check, Loader2, Circle } from "lucide-react";

const STAGES = [
  { key: "detect", label: "Detect" },
  { key: "score", label: "Score" },
  { key: "investigate", label: "Investigate" },
  { key: "decide", label: "Decide" },
  { key: "act", label: "Act" },
  { key: "audit", label: "Audit" },
];

/**
 * Shows the CONNECT->DETECT->SCORE->INVESTIGATE->DECIDE->ACT->AUDIT
 * lifecycle. `completed` is a set of stage keys that have ACTUALLY
 * finished on the backend -- Detect/Score are complete as soon as a
 * cluster is selected (they already ran to produce the cluster list);
 * the rest only mark complete when the corresponding API call has
 * actually returned. No fake progress percentages.
 */
export default function WorkflowStages({ completed, active }) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto rounded-lg border border-border bg-panel px-3 py-2.5">
      {STAGES.map((stage, i) => {
        const isDone = completed.has(stage.key);
        const isActive = active === stage.key;
        return (
          <div key={stage.key} className="flex items-center gap-1 shrink-0">
            <div
              className={`flex items-center gap-1.5 rounded px-2 py-1 text-xs font-medium ${
                isDone
                  ? "text-emerald-400"
                  : isActive
                    ? "text-accent"
                    : "text-text-faint"
              }`}
            >
              {isDone ? (
                <Check className="h-3.5 w-3.5" />
              ) : isActive ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Circle className="h-3 w-3" />
              )}
              {stage.label}
            </div>
            {i < STAGES.length - 1 && <span className="h-px w-4 bg-border" />}
          </div>
        );
      })}
    </div>
  );
}
