import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PolicyPanel from "../components/clusters/PolicyPanel";

describe("PolicyPanel", () => {
  it("shows the AI recommendation and policy decision as visibly separate values", () => {
    const decision = {
      decision: "ESCALATE",
      ai_recommendation: "HOLD_FOR_REVIEW",
      ai_recommendation_followed: false,
      reason_codes: ["CRITICAL_RISK", "AI_DEESCALATION_REJECTED"],
      decision_reason: "Decision ESCALATE based on M3 risk level CRITICAL.",
      policy_version: "v1",
      requires_human_review: true,
    };
    render(<PolicyPanel decision={decision} />);
    expect(screen.getByText("AI Investigator recommends")).toBeInTheDocument();
    expect(screen.getByText("HOLD FOR REVIEW")).toBeInTheDocument();
    expect(screen.getByText("Policy Engine decides")).toBeInTheDocument();
    expect(screen.getByText("ESCALATE")).toBeInTheDocument();
    expect(screen.getByText(/AI recommendation overridden/)).toBeInTheDocument();
  });

  it("does not show a disagreement banner when AI and policy agree", () => {
    const decision = {
      decision: "MONITOR",
      ai_recommendation: "MONITOR",
      ai_recommendation_followed: true,
      reason_codes: ["MEDIUM_RISK"],
      decision_reason: "Decision MONITOR based on M3 risk level MEDIUM.",
      policy_version: "v1",
      requires_human_review: false,
    };
    render(<PolicyPanel decision={decision} />);
    expect(screen.queryByText(/AI recommendation overridden/)).not.toBeInTheDocument();
  });

  it("shows a prompt rather than fabricated data when no decision exists yet", () => {
    render(<PolicyPanel decision={null} />);
    expect(screen.getByText(/Run "Run Full Response"/)).toBeInTheDocument();
  });
});
