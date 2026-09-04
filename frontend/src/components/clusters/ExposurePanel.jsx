import { formatCurrency, formatNumber } from "../../lib/format";

/** Financial context with careful, non-alarmist terminology -- never "fraud loss". */
export default function ExposurePanel({ exposure }) {
  return (
    <div className="rounded-lg border border-border bg-panel p-4">
      <h2 className="text-sm font-semibold text-text">Financial Exposure</h2>
      <p className="mt-0.5 text-[11px] text-text-faint">
        Associated activity, not a confirmed loss figure.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Metric label="Associated Transaction Value" value={formatCurrency(exposure.transaction_value)} />
        <Metric label="Potential Exposure" value={formatCurrency(exposure.estimated_exposure)} emphasize />
        <Metric label="Returned Value" value={formatCurrency(exposure.returned_value)} />
        <Metric label="Transactions" value={`${formatNumber(exposure.transaction_count)} (${formatNumber(exposure.return_count)} returned)`} />
      </div>
    </div>
  );
}

function Metric({ label, value, emphasize }) {
  return (
    <div>
      <div className="text-[11px] text-text-faint">{label}</div>
      <div className={`mt-0.5 text-sm font-semibold tabular-nums ${emphasize ? "text-amber-400" : "text-text"}`}>
        {value}
      </div>
    </div>
  );
}
