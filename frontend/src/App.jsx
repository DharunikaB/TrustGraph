import { useEffect, useState } from "react";
import TopBar from "./components/layout/TopBar";
import DashboardPage from "./pages/DashboardPage";
import ClustersPage from "./pages/ClustersPage";
import EvaluationPage from "./pages/EvaluationPage";
import ValidationResearchPage from "./pages/ValidationResearchPage";
import { ActivityProvider } from "./context/ActivityContext";
import { getHealth } from "./api/clusters";

function pathFromHash() {
  const hash = window.location.hash.replace(/^#/, "");
  return hash || "/";
}

export default function App() {
  const [path, setPath] = useState(pathFromHash());
  const [pendingClusterId, setPendingClusterId] = useState(null);
  const [backendOk, setBackendOk] = useState(true);

  useEffect(() => {
    const onHashChange = () => setPath(pathFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    getHealth()
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false));
  }, [path]);

  const navigate = (to) => {
    window.location.hash = to;
    setPath(to);
  };

  const goToClusterFromDashboard = (clusterId) => {
    setPendingClusterId(clusterId);
    navigate("/clusters");
  };

  return (
    <ActivityProvider>
      <div className="min-h-full">
        <TopBar currentPath={path} onNavigate={navigate} backendOk={backendOk} />
        <main className="mx-auto max-w-[1600px] px-5 py-5">
          {path === "/" && <DashboardPage onSelectCluster={goToClusterFromDashboard} />}
          {path === "/clusters" && (
            <ClustersPage
              initialClusterId={pendingClusterId}
              onClusterConsumed={() => setPendingClusterId(null)}
            />
          )}
          {path === "/evaluation" && <EvaluationPage />}
            {path === "/validation-research" && <ValidationResearchPage />}
        </main>
      </div>
    </ActivityProvider>
  );
}




