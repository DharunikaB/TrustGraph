import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ActionPanel from "../components/clusters/ActionPanel";

describe("ActionPanel", () => {
  it("makes the simulated nature of the action unmistakably clear", () => {
    const action = {
      action_type: "ESCALATE",
      status: "SIMULATED",
      simulation: true,
      target: { cluster_id: "cc-0046" },
      detail: "[SANDBOX SIMULATION -- no real system was contacted] Simulated ESCALATE for cluster cc-0046.",
    };
    render(<ActionPanel action={action} />);
    expect(screen.getByText(/Simulated Action — No real system was contacted/)).toBeInTheDocument();
    expect(screen.getByText("TRUE")).toBeInTheDocument();
    expect(screen.queryByText(/payment blocked/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/account frozen/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/refund issued/i)).not.toBeInTheDocument();
  });

  it("shows a neutral placeholder, not a fabricated action, before any action runs", () => {
    render(<ActionPanel action={null} />);
    expect(screen.getByText("No action executed yet.")).toBeInTheDocument();
  });
});
