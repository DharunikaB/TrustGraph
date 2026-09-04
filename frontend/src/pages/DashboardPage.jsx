import { AlertOctagon, IndianRupee, Search, Zap, Layers } from "lucide-react";
import { getRiskClusters, getStats } from "../api/clusters";
import { useApiData } from "../lib/useApi";
import { useActivity } from "../context/ActivityContext";
import { LoadingState, ErrorState, BackendUnavailableState } from "../components/common/States";
import KpiCard from "../components/dashboard/KpiCard";
import RiskDistributionChart from "../components/dashboard/RiskDistributionChart";
import Badge from "../components/common/Badge";
import { formatCurrency, formatNumber, formatScore, formatDateTime, sortByRiskLevelThenScore } from "../lib/format";

export default function DashboardPage({ onSelectCluster }) {
  const stats = useApiData(() => getStats(), []);
  const clusters = useApiData(() => getRiskClusters(200), []);
  const { investigations, workflowRuns } = useActivity();

  if (clusters.loading && !clusters.data) return <LoadingState label="Loading risk landscape…" />;
  if (clusters.isBackendUnavailable) return <BackendUnavailableState onRetry={clusters.reload} />;
  if (clusters.error) return <ErrorState message={clusters.error.message} onRetry={clusters.reload} />;

  const list = clusters.data?.clusters || [];
  const highCritical = list.filter((c) => ["HIGH", "CRITICAL"].includes(c.risk?.level));
  const potentialExposure = list.reduce((sum, c) => sum + (c.exposure?.estimated_exposure || 0), 0);
  const topClusters = sortByRiskLevelThenScore(list).slice(0, 8);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-bold text-text">Risk Landscape</h1>
        <p className="text-sm text-text-muted">
          TrustGraph payment-abuse intelligence — CONNECT → DETECT → SCORE → INVESTIGATE → DECIDE → ACT → AUDIT
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <KpiCard label="Candidate Clusters" value={formatNumber(clusters.data?.total_candidate_clusters)} icon={Layers} />
        <KpiCard
          label="High / Critical Risk"
          value={formatNumber(highCritical.length)}
          icon={AlertOctagon}
          accent="text-orange-400"
        />
        <KpiCard label="Potential Exposure" value={formatCurrency(potentialExposure)} icon={IndianRupee} accent="text-amber-400" />
        <KpiCard
          label="Investigations (session)"
          value={formatNumber(investigations.length)}
          sublabel="Triggered this session"
          icon={Search}
        />
        <KpiCard
          label="Actions / Reviews (session)"
          value={formatNumber(workflowRuns.length)}
          sublabel="Triggered this session"
          icon={Zap}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-lg border border-border bg-panel p-4 lg:col-span-1">
          <h2 className="mb-2 text-sm font-semibold text-text">Risk Distribution</h2>
          <RiskDistributionChart clusters={list} />
        </div>

        <div className="rounded-lg border border-border bg-panel p-4 lg:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text">Top Candidate Clusters</h2>
            <button
              type="button"
              onClick={() => onSelectCluster(null)}
              className="text-xs text-accent hover:underline"
            >
              View all →
            </button>
          </div>
          <div className="divide-y divide-border">
            {topClusters.map((c) => (
              <button
                key={c.cluster_id}
                type="button"
                onClick={() => onSelectCluster(c.cluster_id)}
                className="flex w-full items-center justify-between gap-3 py-2 text-left hover:bg-panel-raised px-2 -mx-2 rounded transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Badge value={c.risk?.level} />
                  <span className="font-mono text-xs text-text-muted truncate">{c.cluster_id}</span>
                </div>
                <div className="flex items-center gap-4 shrink-0 text-xs text-text-muted">
                  <span>{c.customers?.length ?? 0} customers</span>
                  <span className="font-semibold text-text tabular-nums">{formatScore(c.risk?.score)}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ActivityList
          title="Recent Investigations"
          items={investigations}
          renderMeta={(item) => (
            <Badge value={item.result?.assessment?.classification} kind="level" />
          )}
        />
        <ActivityList
          title="Recent Actions"
          items={workflowRuns}
          renderMeta={(item) => <Badge value={item.result?.policy_decision?.decision} kind="action" />}
        />
      </div>

      {stats.data && (
        <p className="text-xs text-text-faint">
          Dataset: {formatNumber(stats.data.merchants)} merchants · {formatNumber(stats.data.customers)} customers ·{" "}
          {formatNumber(stats.data.transactions)} transactions
        </p>
      )}
    </div>
  );
}

function ActivityList({ title, items, renderMeta }) {
  return (
    <div className="rounded-lg border border-border bg-panel p-4">
      <h2 className="mb-2 text-sm font-semibold text-text">{title}</h2>
      {items.length === 0 ? (
        <p className="py-4 text-center text-xs text-text-faint">
          None yet — investigate a cluster to populate this list.
        </p>
      ) : (
        <div className="divide-y divide-border">
          {items.slice(0, 6).map((item, i) => (
            <div key={i} className="flex items-center justify-between gap-3 py-2 text-xs">
              <div className="min-w-0">
                <span className="font-mono text-text-muted">{item.clusterId}</span>
                <span className="ml-2 text-text-faint">{formatDateTime(item.at)}</span>
              </div>
              {renderMeta(item)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
