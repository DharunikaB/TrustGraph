import { Zap, FlaskConical } from "lucide-react";
import Badge from "../common/Badge";

/**
 * Displays M5's sandbox ActionResult. `simulation: true` is ALWAYS
 * true in this project (SandboxActionExecutor is the only executor
 * implementation) -- this panel makes that fact impossible to miss,
 * and never phrases anything as if a real payment/customer action
 * occurred.
 */
export default function ActionPanel({ action }) {
  if (!action) {
    return (
      <div className="rounded-lg border border-border bg-panel p-4">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-text">
          <Zap className="h-4 w-4 text-accent" />
          Autonomous Response
        </h2>
        <p className="mt-2 text-xs text-text-faint">No action executed yet.</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-panel p-4">
      <h2 className="flex items-center gap-1.5 text-sm font-semibold text-text">
        <Zap className="h-4 w-4 text-accent" />
        Autonomous Response
      </h2>

      <div className="mt-3 rounded border-2 border-dashed border-amber-500/50 bg-amber-500/5 px-3 py-2">
        <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-amber-400">
          <FlaskConical className="h-3.5 w-3.5" />
          Simulated Action — No real system was contacted
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
        <div>
          <div className="text-text-faint">Action</div>
          <Badge value={action.action_type} kind="action" className="mt-0.5" />
        </div>
        <div>
          <div className="text-text-faint">Execution Status</div>
          <Badge value={action.status} kind="status" className="mt-0.5" />
        </div>
        <div>
          <div className="text-text-faint">Simulation</div>
          <div className="mt-0.5 font-mono font-semibold text-amber-400">
            {String(action.simulation).toUpperCase()}
          </div>
        </div>
        <div>
          <div className="text-text-faint">Target Cluster</div>
          <div className="mt-0.5 font-mono text-text-muted">{action.target?.cluster_id}</div>
        </div>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-text-muted">{action.detail}</p>
      {action.duplicate_of_action_id && (
        <p className="mt-1 text-[11px] text-text-faint">
          Duplicate of already-executed action <span className="font-mono">{action.duplicate_of_action_id}</span> —
          no new effect was simulated.
        </p>
      )}
    </div>
  );
}
