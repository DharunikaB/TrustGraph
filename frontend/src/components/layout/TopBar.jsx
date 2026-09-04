import { ShieldAlert, Circle } from "lucide-react";
import { NavLink } from "./NavLink";

const TABS = [
  { to: "/", label: "Dashboard" },
  { to: "/clusters", label: "Clusters" },
  { to: "/evaluation", label: "Evaluation" },
  { to: "/validation-research", label: "Validation Research" },
];

export default function TopBar({ currentPath, onNavigate, backendOk }) {
  return (
    <header className="border-b border-border bg-panel">
      <div className="flex items-center justify-between px-5 py-3">
        <div className="flex items-center gap-3">
          <ShieldAlert className="h-5 w-5 text-accent" />
          <span className="text-sm font-bold tracking-wide text-text">TRUSTGRAPH</span>
          <span className="rounded border border-border-strong px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            Environment: Simulation
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <Circle
            className={`h-2 w-2 ${backendOk ? "fill-success text-success" : "fill-danger text-danger"}`}
          />
          {backendOk ? "Backend connected" : "Backend unavailable"}
        </div>
      </div>
      <nav className="flex gap-1 px-5">
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} active={currentPath === tab.to} onNavigate={onNavigate}>
            {tab.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}

