import Badge from "../common/Badge";
import { formatCurrency, formatScore, sortByRiskLevelThenScore } from "../../lib/format";

export default function ClusterList({ clusters, selectedId, onSelect }) {
  const sorted = sortByRiskLevelThenScore(clusters);

  return (
    <div className="flex h-full flex-col rounded-lg border border-border bg-panel">
      <div className="border-b border-border px-3 py-2.5">
        <h2 className="text-sm font-semibold text-text">Candidate Clusters</h2>
        <p className="text-xs text-text-faint">{clusters.length} sorted by risk</p>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sorted.map((c) => {
          const active = c.cluster_id === selectedId;
          return (
            <button
              key={c.cluster_id}
              type="button"
              onClick={() => onSelect(c.cluster_id)}
              className={`block w-full border-b border-border px-3 py-2.5 text-left transition-colors ${
                active ? "bg-accent-soft border-l-2 border-l-accent" : "hover:bg-panel-raised border-l-2 border-l-transparent"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs text-text">{c.cluster_id}</span>
                <Badge value={c.risk?.level} />
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-text-muted">
                <span>{c.customers?.length ?? 0} customers</span>
                <span className="font-semibold tabular-nums text-text">{formatScore(c.risk?.score)}</span>
              </div>
              <div className="mt-0.5 text-[11px] text-text-faint">
                Exposure {formatCurrency(c.exposure?.estimated_exposure)}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
