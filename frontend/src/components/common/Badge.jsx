import { levelStyle, actionStyle, statusStyle } from "../../lib/severity";

const KIND_RESOLVERS = { level: levelStyle, action: actionStyle, status: statusStyle };

/** A small, consistent pill used everywhere risk level / action / status appears. */
export default function Badge({ value, kind = "level", className = "" }) {
  if (!value) return <span className="text-text-faint text-xs">—</span>;
  const style = (KIND_RESOLVERS[kind] || levelStyle)(value);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs font-semibold tracking-wide ${style.bg} ${style.border} ${style.text} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {value.replace(/_/g, " ")}
    </span>
  );
}
