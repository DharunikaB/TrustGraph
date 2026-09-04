import { createContext, useContext, useMemo, useState, useCallback } from "react";

/**
 * Tracks investigations/workflow runs actually triggered THIS session,
 * from real API responses -- never a fabricated lifetime count. The
 * backend has no endpoint listing "all investigations ever run" (M4/M5
 * don't persist a history), so a dashboard KPI claiming a total would
 * be invented. This context instead honestly represents "what has this
 * analyst actually done in this session", clearly labeled as such
 * wherever it's displayed (see DashboardPage).
 */
const ActivityContext = createContext(null);

export function ActivityProvider({ children }) {
  const [investigations, setInvestigations] = useState([]);
  const [workflowRuns, setWorkflowRuns] = useState([]);

  const recordInvestigation = useCallback((clusterId, result) => {
    setInvestigations((prev) => [
      { clusterId, result, at: new Date().toISOString() },
      ...prev,
    ].slice(0, 20));
  }, []);

  const recordWorkflowRun = useCallback((clusterId, result) => {
    setWorkflowRuns((prev) => [
      { clusterId, result, at: new Date().toISOString() },
      ...prev,
    ].slice(0, 20));
  }, []);

  const value = useMemo(
    () => ({ investigations, workflowRuns, recordInvestigation, recordWorkflowRun }),
    [investigations, workflowRuns, recordInvestigation, recordWorkflowRun]
  );

  return <ActivityContext.Provider value={value}>{children}</ActivityContext.Provider>;
}

export function useActivity() {
  const ctx = useContext(ActivityContext);
  if (!ctx) throw new Error("useActivity must be used within ActivityProvider");
  return ctx;
}
