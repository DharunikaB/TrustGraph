import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { BackendUnavailableState, ErrorState } from "../components/common/States";

describe("BackendUnavailableState", () => {
  it("shows a clear message instead of a blank screen", () => {
    render(<BackendUnavailableState />);
    expect(screen.getByText("TrustGraph backend unavailable")).toBeInTheDocument();
  });

  it("calls onRetry when the retry button is clicked", () => {
    const onRetry = vi.fn();
    render(<BackendUnavailableState onRetry={onRetry} />);
    fireEvent.click(screen.getByText("Retry"));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("ErrorState", () => {
  it("displays the actual error message rather than a generic one", () => {
    render(<ErrorState message="Investigation failed: timeout" />);
    expect(screen.getByText("Investigation failed: timeout")).toBeInTheDocument();
  });
});
