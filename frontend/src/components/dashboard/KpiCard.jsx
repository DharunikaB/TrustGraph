export default function KpiCard({ label, value, sublabel, icon: Icon, accent = "text-text" }) {
  return (
    <div className="rounded-lg border border-border bg-panel px-4 py-3.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-text-faint" />}
      </div>
      <div className={`mt-1.5 text-2xl font-bold tabular-nums ${accent}`}>{value}</div>
      {sublabel && <div className="mt-0.5 text-xs text-text-faint">{sublabel}</div>}
    </div>
  );
}
