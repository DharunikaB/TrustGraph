import Badge from "../common/Badge";
import { formatScore } from "../../lib/format";

/** Shows M3's score/level and the ACTUAL contributor breakdown -- never recomputed. */
export default function RiskPanel({ cluster }) {
  const risk = cluster.risk;

  return (
    <div className="rounded-lg border border-border bg-panel p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text">Risk Assessment</h2>
        <Badge value={risk.level} />
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-3xl font-bold tabular-nums text-text">{formatScore(risk.score)}</span>
        <span className="text-xs text-text-faint">/ 100 (M3 deterministic score)</span>
      </div>

      <h3 className="mt-4 mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
        Why this cluster is risky
      </h3>
      <div className="space-y-2">
        {risk.contributors
          .slice()
          .sort((a, b) => b.contribution - a.contribution)
          .map((c) => (
            <ContributorBar key={c.signal} contributor={c} />
          ))}
      </div>
    </div>
  );
}

function ContributorBar({ contributor }) {
  const pct = Math.min(100, (contributor.contribution / contributor.max_contribution) * 100);
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-text">{formatSignalName(contributor.signal)}</span>
        <span className="font-semibold tabular-nums text-text">
          +{contributor.contribution.toFixed(1)}
          <span className="text-text-faint"> / {contributor.max_contribution.toFixed(0)}</span>
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-border">
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1 text-[11px] leading-snug text-text-muted">{contributor.evidence}</p>
    </div>
  );
}

function formatSignalName(signal) {
  return signal
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}
