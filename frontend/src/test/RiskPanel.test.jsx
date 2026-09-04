import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import RiskPanel from "../components/clusters/RiskPanel";

const cluster = {
  risk: {
    score: 76.06,
    level: "CRITICAL",
    contributors: [
      { signal: "account_creation_burst", contribution: 20, max_contribution: 20, evidence: "3 of 3 created in one window." },
      { signal: "return_anomaly", contribution: 13.4, max_contribution: 15, evidence: "Return rate 61.1%." },
    ],
  },
};

describe("RiskPanel", () => {
  it("displays the backend-provided risk score and level, not a recomputed one", () => {
    render(<RiskPanel cluster={cluster} />);
    expect(screen.getByText("76.1")).toBeInTheDocument();
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
  });

  it("renders each contributor's actual backend contribution value", () => {
    render(<RiskPanel cluster={cluster} />);
    expect(screen.getByText(/\+20\.0/)).toBeInTheDocument();
    expect(screen.getByText(/3 of 3 created in one window\./)).toBeInTheDocument();
  });
});
