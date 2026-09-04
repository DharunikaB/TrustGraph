import { useMemo, useState } from "react";
import ReactFlow, { Background, Controls, MarkerType } from "reactflow";
import "reactflow/dist/style.css";
import GraphNode from "./GraphNode";

const nodeTypes = { entity: GraphNode };

const EDGE_COLOR = { USES_DEVICE: "#a78bfa", CONNECTED_FROM: "#5eead4" };

/**
 * Deterministic layered layout -- no random placement, no heavy layout
 * dependency. Hubs (devices/networks) form the top row; customers form
 * the bottom row, evenly spaced. This directly visualizes the bipartite
 * relationship graph M2 builds: shared infrastructure is obvious because
 * multiple customer nodes converge on the same hub node.
 */
function layoutGraph(rawNodes, rawEdges) {
  const hubs = rawNodes.filter((n) => n.type !== "customer");
  const customers = rawNodes.filter((n) => n.type === "customer");

  const spacingX = 150;
  const hubRowY = 40;
  const customerRowY = 220;

  const hubStartX = (Math.max(customers.length, hubs.length, 1) * spacingX - hubs.length * spacingX) / 2;
  const customerStartX = (Math.max(customers.length, hubs.length, 1) * spacingX - customers.length * spacingX) / 2;

  const positioned = [
    ...hubs.map((n, i) => ({ ...n, x: hubStartX + i * spacingX, y: hubRowY })),
    ...customers.map((n, i) => ({ ...n, x: customerStartX + i * spacingX, y: customerRowY })),
  ];

  const nodes = positioned.map((n) => ({
    id: n.id,
    type: "entity",
    position: { x: n.x, y: n.y },
    data: { entityType: n.type, fullId: n.entity_id },
  }));

  const edges = rawEdges.map((e, i) => ({
    id: `e-${i}`,
    source: e.source,
    target: e.target,
    style: { stroke: EDGE_COLOR[e.type] || "#3a3f4b", strokeWidth: 1.5 },
    markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLOR[e.type] || "#3a3f4b", width: 14, height: 14 },
  }));

  return { nodes, edges };
}

export default function ClusterGraph({ graphData, onSelectNode }) {
  const { nodes, edges } = useMemo(
    () => layoutGraph(graphData?.nodes || [], graphData?.edges || []),
    [graphData]
  );
  const [selectedId, setSelectedId] = useState(null);

  const handleNodeClick = (_event, node) => {
    setSelectedId(node.id);
    onSelectNode?.({ id: node.id, type: node.data.entityType, entityId: node.data.fullId });
  };

  return (
    <div className="rounded-lg border border-border bg-panel-raised">
      <div className="h-[300px]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          proOptions={{ hideAttribution: true }}
          minZoom={0.3}
          maxZoom={2}
        >
          <Background color="#2a2e38" gap={20} size={1} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <div className="flex items-center gap-4 border-t border-border px-3 py-1.5 text-[10px] text-text-faint">
        <LegendSwatch color={EDGE_COLOR.USES_DEVICE} label="Uses device" />
        <LegendSwatch color={EDGE_COLOR.CONNECTED_FROM} label="Connected from network" />
      </div>
      {selectedId && (
        <div className="sr-only" aria-live="polite">
          Selected node {selectedId}
        </div>
      )}
    </div>
  );
}

function LegendSwatch({ color, label }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-0.5 w-4 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
