import { Handle, Position } from "reactflow";
import { User, Smartphone, Wifi } from "lucide-react";
import { shortId } from "../../lib/format";

const TYPE_META = {
  customer: { icon: User, label: "Customer", ring: "ring-sky-500/50", bg: "bg-sky-500/10", text: "text-sky-300" },
  device: { icon: Smartphone, label: "Device", ring: "ring-violet-500/50", bg: "bg-violet-500/10", text: "text-violet-300" },
  network: { icon: Wifi, label: "Network", ring: "ring-teal-500/50", bg: "bg-teal-500/10", text: "text-teal-300" },
};

export default function GraphNode({ data }) {
  const meta = TYPE_META[data.entityType] || TYPE_META.customer;
  const Icon = meta.icon;
  return (
    <div
      className={`flex flex-col items-center gap-1 rounded-lg border border-border ${meta.bg} px-3 py-2 ring-1 ${meta.ring} min-w-[110px]`}
      title={data.fullId}
    >
      <Handle type="target" position={Position.Top} className="!bg-border-strong !border-0 !h-1.5 !w-1.5" />
      <Handle type="source" position={Position.Bottom} className="!bg-border-strong !border-0 !h-1.5 !w-1.5" />
      <Icon className={`h-4 w-4 ${meta.text}`} />
      <span className={`text-[10px] font-semibold uppercase tracking-wide ${meta.text}`}>{meta.label}</span>
      <span className="font-mono text-[10px] text-text-muted">{shortId(data.fullId, 8)}</span>
    </div>
  );
}
