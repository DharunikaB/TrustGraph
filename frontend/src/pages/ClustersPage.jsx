import { useEffect, useMemo, useState } from "react";
import { Play } from "lucide-react";
import { getRiskClusters, getClusterGraph } from "../api/clusters";
import { investigateCluster } from "../api/investigations";
import { respondToCluster, getAuditTrail } from "../api/workflow";
import { useApiData, useApiAction } from "../lib/useApi";
import { useActivity } from "../context/ActivityContext";
import { LoadingState, ErrorState, BackendUnavailableState, EmptyState } from "../components/common/States";
import ClusterList from "../components/clusters/ClusterList";
import ClusterGraph from "../components/clusters/ClusterGraph";
import NodeDetailPanel from "../components/clusters/NodeDetailPanel";
import RiskPanel from "../components/clusters/RiskPanel";
import ExposurePanel from "../components/clusters/ExposurePanel";
import EvidencePanel from "../components/clusters/EvidencePanel";
import InvestigationPanel from "../components/clusters/InvestigationPanel";
import PolicyPanel from "../components/clusters/PolicyPanel";
import ActionPanel from "../components/clusters/ActionPanel";
import AuditTimeline from "../components/clusters/AuditTimeline";
import WorkflowStages from "../components/clusters/WorkflowStages";

export default function ClustersPage({ initialClusterId, onClusterConsumed }) {
  const clustersQuery = useApiData(() => getRiskClusters(200), []);
  const [selectedId, setSelectedId] = useState(initialClusterId || null);
  const [selectedNode, setSelectedNode] = useState(null);
  const { recordInvestigation, recordWorkflowRun } = useActivity();

  const investigateAction = useApiAction(investigateCluster);
  const respondAction = useApiAction(respondToCluster);
  const auditQuery = useApiAction(getAuditTrail);
  const graphQuery = useApiAction(getClusterGraph);

  const clusters = useMemo(() => clustersQuery.data?.clusters || [], [clustersQuery.data]);
  const cluster = useMemo(() => clusters.find((c) => c.cluster_id === selectedId) || null, [clusters, selectedId]);

  // Pick a sensible default once clusters load, if nothing selected yet.
  // Depends on clusters.length (a stable primitive) rather than the
  // `clusters` array itself, which is a new reference every render due
  // to the `|| []` fallback above -- listing the array would re-run
  // this effect on every render for no reason.
  useEffect(() => {
    if (!selectedId && clusters.length > 0) {
      setSelectedId(clusters[0].cluster_id);
    }
  }, [clusters, selectedId]);

  useEffect(() => {
    if (initialClusterId) onClusterConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialClusterId]);

  // Reset per-cluster workflow state whenever the selection changes.
  useEffect(() => {
    if (!selectedId) return;
    setSelectedNode(null);
    investigateAction.reset();
    respondAction.reset();
    auditQuery.reset();
    graphQuery.reset();
    graphQuery.run(selectedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const handleInvestigate = async () => {
    if (!cluster) return;
    try {
      const result = await investigateAction.run(cluster.cluster_id);
      recordInvestigation(cluster.cluster_id, result);
    } catch {
      // surfaced via investigateAction.error in the panel
    }
  };

  const handleRunFullResponse = async () => {
    if (!cluster) return;
    try {
      const result = await respondAction.run(cluster.cluster_id);
      recordWorkflowRun(cluster.cluster_id, result);
      const audit = await auditQuery.run(cluster.cluster_id);
      return { result, audit };
    } catch {
      // surfaced via respondAction.error
    }
  };

  if (clustersQuery.loading && !clustersQuery.data) return <LoadingState label="Loading candidate clusters…" />;
  if (clustersQuery.isBackendUnavailable) return <BackendUnavailableState onRetry={clustersQuery.reload} />;
  if (clustersQuery.error) return <ErrorState message={clustersQuery.error.message} onRetry={clustersQuery.reload} />;
  if (clusters.length === 0) return <EmptyState message="No candidate clusters in the current dataset." />;

  // The investigation shown is either the standalone one, or the one
  // embedded in the full workflow response (whichever ran most recently).
  const activeInvestigation = respondAction.data?.investigation || investigateAction.data || null;
  const policyDecision = respondAction.data?.policy_decision || null;
  const action = respondAction.data?.action || null;
  const auditEvents = auditQuery.data?.events || [];

  const completedStages = new Set(["detect", "score"]);
  if (activeInvestigation) completedStages.add("investigate");
  if (policyDecision) completedStages.add("decide");
  if (action) completedStages.add("act");
  if (auditEvents.length > 0) completedStages.add("audit");
  const activeStage = investigateAction.loading
    ? "investigate"
    : respondAction.loading
      ? !policyDecision
        ? "investigate"
        : !action
          ? "decide"
          : "act"
      : null;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr_360px] lg:h-[calc(100vh-140px)]">
      <div className="lg:overflow-y-auto lg:pr-1">
        <ClusterList clusters={clusters} selectedId={selectedId} onSelect={setSelectedId} />
      </div>

      <div className="min-w-0 space-y-4 lg:overflow-y-auto lg:pr-1">
        <WorkflowStages completed={completedStages} active={activeStage} />

        {graphQuery.data && !graphQuery.data.error && (
          <div>
            <ClusterGraph graphData={graphQuery.data} onSelectNode={setSelectedNode} />
            {cluster && <NodeDetailPanel node={selectedNode} cluster={cluster} />}
          </div>
        )}

        {cluster && <ExposurePanel exposure={cluster.exposure} />}
        {cluster && <EvidencePanel signals={cluster.signals} evidence={cluster.evidence} />}

        <div className="flex justify-end">
          <button
            type="button"
            onClick={handleRunFullResponse}
            disabled={respondAction.loading}
            className="flex items-center gap-2 rounded bg-accent px-4 py-2 text-sm font-semibold text-black hover:bg-orange-400 disabled:opacity-50 transition-colors"
          >
            <Play className="h-4 w-4" />
            {respondAction.loading ? "Running full response…" : "Run Full Response (Investigate → Policy → Action → Audit)"}
          </button>
        </div>
        {respondAction.error && (
          <p className="rounded border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-red-300">
            Workflow failed: {respondAction.error.message}
          </p>
        )}

        <InvestigationPanel
          investigation={activeInvestigation}
          loading={investigateAction.loading}
          error={investigateAction.error}
          onInvestigate={handleInvestigate}
        />
        <PolicyPanel decision={policyDecision} />
        <ActionPanel action={action} />
        <AuditTimeline events={auditEvents} />
      </div>

      <div className="space-y-4 lg:overflow-y-auto lg:pr-1">{cluster && <RiskPanel cluster={cluster} />}</div>
    </div>
  );
}
