/** Shown when a graph node is selected -- minimal, non-sensitive detail only. */
export default function NodeDetailPanel({ node, cluster }) {
  if (!node) return null;

  let title = "";
  let rows = [];

  if (node.type === "customer") {
    title = "Customer";
    const txCount = cluster.transactions?.length ?? 0;
    rows = [
      ["Customer ID", node.entityId],
      ["Transactions in cluster", String(txCount)],
      ["Cluster risk level", cluster.risk?.level],
    ];
  } else if (node.type === "device") {
    title = "Device";
    const info = cluster.signals?.shared_device;
    rows = [
      ["Device ID", node.entityId],
      ["Customers on this device (cluster)", String(info?.max_customers_per_device ?? "—")],
    ];
  } else if (node.type === "network") {
    title = "Network";
    const info = cluster.signals?.shared_network;
    rows = [
      ["Network ID", node.entityId],
      ["Customers on this network (cluster)", String(info?.max_customers_per_network ?? "—")],
    ];
  }

  return (
    <div className="mt-2 rounded border border-border-strong bg-panel-raised px-3 py-2 text-xs">
      <div className="font-semibold text-text">{title}</div>
      <dl className="mt-1 space-y-0.5">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3">
            <dt className="text-text-faint">{label}</dt>
            <dd className="truncate font-mono text-text-muted" title={value}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
