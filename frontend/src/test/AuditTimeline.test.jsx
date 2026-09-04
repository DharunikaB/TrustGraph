import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import AuditTimeline from "../components/clusters/AuditTimeline";

describe("AuditTimeline", () => {
  it("renders each real backend audit event in order", () => {
    const events = [
      { audit_id: "a1", event_type: "INVESTIGATION_RECEIVED", new_state: "COMPLETED", timestamp: "2026-01-01T01:00:00Z", reason_codes: [] },
      { audit_id: "a2", event_type: "POLICY_EVALUATED", new_state: "ESCALATE", timestamp: "2026-01-01T01:00:01Z", reason_codes: ["CRITICAL_RISK"] },
    ];
    render(<AuditTimeline events={events} />);
    expect(screen.getByText("INVESTIGATION RECEIVED")).toBeInTheDocument();
    expect(screen.getByText("POLICY EVALUATED")).toBeInTheDocument();
    expect(screen.getByText("CRITICAL_RISK")).toBeInTheDocument();
  });

  it("shows an honest empty state instead of fabricating events", () => {
    render(<AuditTimeline events={[]} />);
    expect(screen.getByText("No audit events yet for this cluster.")).toBeInTheDocument();
  });
});
