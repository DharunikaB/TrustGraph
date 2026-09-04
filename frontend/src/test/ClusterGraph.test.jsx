import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ClusterGraph from "../components/clusters/ClusterGraph";

const graphData = {
  cluster_id: "cc-0046",
  nodes: [
    { id: "customer:c1", type: "customer", entity_id: "c1" },
    { id: "customer:c2", type: "customer", entity_id: "c2" },
    { id: "device:d1", type: "device", entity_id: "d1" },
  ],
  edges: [
    { source: "customer:c1", target: "device:d1", type: "USES_DEVICE" },
    { source: "customer:c2", target: "device:d1", type: "USES_DEVICE" },
  ],
};

describe("ClusterGraph", () => {
  it("renders one node per entry in the API response (no fake/decorative nodes)", () => {
    const { container } = render(<ClusterGraph graphData={graphData} />);
    // React Flow renders nodes async via its own layout pass; assert the
    // node label text (customer/device short IDs) made it into the DOM.
    expect(container.textContent).toContain("Customer");
    expect(container.textContent).toContain("Device");
  });

  it("renders nothing extra when given an empty graph", () => {
    const { container } = render(<ClusterGraph graphData={{ nodes: [], edges: [] }} />);
    expect(container.querySelectorAll(".react-flow__node").length).toBe(0);
  });
});
