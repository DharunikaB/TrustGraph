import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

const SIGNAL_LABELS = {
  shared_device: "Shared Device",
  shared_network: "Shared Network",
  account_creation_burst: "Account Creation Burst",
  transaction_velocity: "Transaction Velocity",
  transaction_coordination: "Transaction Coordination",
  return_anomaly: "Return Anomaly",
  graph_connectivity: "Graph Connectivity",
};

// Raw ID-keyed breakdowns aren't useful to show in the UI directly --
// the aggregate fields (ratio, counts) already summarize them.
const HIDDEN_FIELDS = new Set([
  "device_customer_counts_in_cluster",
  "device_customer_counts_dataset_wide",
  "network_customer_counts_in_cluster",
  "network_customer_counts_dataset_wide",
]);

/**
 * Expandable per-signal evidence -- deliberately phrased as observations
 * ("shared device detected") not verdicts ("shared device = fraud").
 * All values come directly from M2's signals object.
 */
export default function EvidencePanel({ signals, evidence }) {
  const [expanded, setExpanded] = useState(() => new Set());

  const toggle = (name) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  return (
    <div className="rounded-lg border border-border bg-panel p-4">
      <h2 className="text-sm font-semibold text-text">Signal Evidence</h2>
      <p className="mt-0.5 text-[11px] text-text-faint">
        Individual signals are supporting evidence, not standalone proof of abuse.
      </p>

      {evidence?.length > 0 && (
        <ul className="mt-3 space-y-1 border-b border-border pb-3 text-xs text-text-muted">
          {evidence.map((line, i) => (
            <li key={i} className="flex gap-1.5">
              <span className="text-accent">•</span>
              {line}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 divide-y divide-border">
        {Object.entries(signals).map(([name, values]) => {
          const isOpen = expanded.has(name);
          const fields = Object.entries(values).filter(([k]) => !HIDDEN_FIELDS.has(k));
          return (
            <div key={name} className="py-2">
              <button
                type="button"
                onClick={() => toggle(name)}
                className="flex w-full items-center gap-1.5 text-left text-xs font-medium text-text hover:text-accent"
                aria-expanded={isOpen}
              >
                {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                {SIGNAL_LABELS[name] || name}
                <span className="ml-auto font-normal text-text-faint">detected</span>
              </button>
              {isOpen && (
                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 pl-5 text-[11px]">
                  {fields.map(([key, value]) => (
                    <div key={key} className="contents">
                      <dt className="text-text-faint">{key.replace(/_/g, " ")}</dt>
                      <dd className="text-right font-mono text-text-muted">{formatValue(value)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatValue(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return Number.isInteger(value) ? value : value.toFixed(3);
  return String(value);
}
