import { CheckCircle2, XCircle, Copy, AlertCircle, Eye } from "lucide-react";
import { formatTimestamp } from "../../lib/format";

const EVENT_META = {
  INVESTIGATION_RECEIVED: { icon: Eye, color: "text-sky-400" },
  POLICY_EVALUATED: { icon: CheckCircle2, color: "text-violet-400" },
  DECISION_CREATED: { icon: CheckCircle2, color: "text-violet-400" },
  ACTION_REQUESTED: { icon: Eye, color: "text-text-muted" },
  ACTION_EXECUTED: { icon: CheckCircle2, color: "text-emerald-400" },
  ACTION_REJECTED: { icon: XCircle, color: "text-red-400" },
  ACTION_DUPLICATE: { icon: Copy, color: "text-amber-400" },
  ACTION_FAILED: { icon: XCircle, color: "text-red-400" },
  HUMAN_REVIEW_REQUIRED: { icon: AlertCircle, color: "text-orange-400" },
};

/** Chronological audit trail -- Observe -> Investigate -> Decide -> Act -> Audit. */
export default function AuditTimeline({ events }) {
  if (!events || events.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-panel p-4">
        <h2 className="text-sm font-semibold text-text">Audit Trail</h2>
        <p className="mt-2 text-xs text-text-faint">No audit events yet for this cluster.</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-panel p-4">
      <h2 className="text-sm font-semibold text-text">Audit Trail</h2>
      <ol className="mt-3 space-y-0">
        {events.map((event, i) => {
          const meta = EVENT_META[event.event_type] || { icon: Eye, color: "text-text-muted" };
          const Icon = meta.icon;
          return (
            <li key={event.audit_id} className="relative flex gap-3 pb-4 last:pb-0">
              {i < events.length - 1 && (
                <span className="absolute left-[9px] top-5 h-full w-px bg-border" aria-hidden="true" />
              )}
              <Icon className={`z-10 h-[18px] w-[18px] shrink-0 ${meta.color} bg-panel`} />
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-text">{event.event_type.replace(/_/g, " ")}</span>
                  <span className="font-mono text-[10px] text-text-faint">{formatTimestamp(event.timestamp)}</span>
                </div>
                {event.new_state && (
                  <div className="mt-0.5 text-[11px] text-text-muted">
                    → <span className="font-mono">{event.new_state}</span>
                  </div>
                )}
                {event.reason_codes?.length > 0 && (
                  <div className="mt-0.5 text-[10px] text-text-faint">{event.reason_codes.join(", ")}</div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
