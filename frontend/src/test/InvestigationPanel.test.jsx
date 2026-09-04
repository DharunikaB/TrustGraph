import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import InvestigationPanel from "../components/clusters/InvestigationPanel";

describe("InvestigationPanel", () => {
  it("calls onInvestigate when the button is clicked", () => {
    const onInvestigate = vi.fn();
    render(<InvestigationPanel investigation={null} loading={false} error={null} onInvestigate={onInvestigate} />);
    fireEvent.click(screen.getByText("Investigate Cluster"));
    expect(onInvestigate).toHaveBeenCalledOnce();
  });

  it("shows a plain loading state, never a fake result, while loading", () => {
    render(<InvestigationPanel investigation={null} loading={true} error={null} onInvestigate={() => {}} />);
    expect(screen.getByText("Analyzing cluster evidence…")).toBeInTheDocument();
    expect(screen.queryByText(/POTENTIAL_COORDINATED_ABUSE/)).not.toBeInTheDocument();
  });

  it("shows a controlled error message on failure, not a fabricated AI response", () => {
    render(
      <InvestigationPanel
        investigation={null}
        loading={false}
        error={new Error("Request failed (500)")}
        onInvestigate={() => {}}
      />
    );
    expect(screen.getByText(/Investigation request failed/)).toBeInTheDocument();
    expect(screen.getByText(/Request failed \(500\)/)).toBeInTheDocument();
  });

  it("renders a completed investigation's real backend fields", () => {
    const investigation = {
      status: "COMPLETED",
      assessment: { classification: "POTENTIAL_COORDINATED_ABUSE", severity: "CRITICAL", confidence: 0.88 },
      summary: "Test summary from backend.",
      key_findings: [{ finding: "Finding A", evidence_refs: ["account_creation_burst"] }],
      supporting_evidence: ["Support A"],
      contradicting_evidence: ["Contradiction A"],
      investigation_recommendations: ["Recommendation A"],
      recommended_action: "HOLD_FOR_REVIEW",
    };
    render(<InvestigationPanel investigation={investigation} loading={false} error={null} onInvestigate={() => {}} />);
    expect(screen.getByText("POTENTIAL COORDINATED ABUSE")).toBeInTheDocument();
    expect(screen.getByText("88%")).toBeInTheDocument();
    expect(screen.getByText("Test summary from backend.")).toBeInTheDocument();
    expect(screen.getByText("HOLD FOR REVIEW")).toBeInTheDocument();
  });

  it("never shows an AI-unavailable investigation as if it completed", () => {
    render(
      <InvestigationPanel
        investigation={{ status: "AI_UNAVAILABLE", metadata: { error: "GEMINI_API_KEY is not configured." } }}
        loading={false}
        error={null}
        onInvestigate={() => {}}
      />
    );
    expect(screen.getByText(/GEMINI_API_KEY is not configured\./)).toBeInTheDocument();
    expect(screen.queryByText("Key Findings")).not.toBeInTheDocument();
  });
});
