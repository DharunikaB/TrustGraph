/** Shared formatting helpers -- pure presentation, no business logic. */

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

export function formatCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return inr.format(value);
}

export function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-IN").format(value);
}

export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatScore(value) {
  if (value === null || value === undefined) return "—";
  return Number(value).toFixed(1);
}

export function formatTimestamp(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString("en-IN", { hour12: false }) + "." + String(date.getMilliseconds()).padStart(3, "0");
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-IN", { hour12: false });
}

/** Shortens a UUID for display without hiding the full value (title attr). */
export function shortId(id, len = 8) {
  if (!id) return "—";
  return id.length > len ? `${id.slice(0, len)}…` : id;
}

const RISK_LEVEL_ORDER = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

export function sortByRiskLevelThenScore(clusters) {
  return [...clusters].sort((a, b) => {
    const la = RISK_LEVEL_ORDER[a.risk?.level] ?? 99;
    const lb = RISK_LEVEL_ORDER[b.risk?.level] ?? 99;
    if (la !== lb) return la - lb;
    return (b.risk?.score ?? 0) - (a.risk?.score ?? 0);
  });
}
