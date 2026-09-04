import { describe, it, expect, vi, afterEach } from "vitest";
import { apiGet, apiPost, ApiError, BackendUnavailableError, API_BASE_URL } from "../api/client";
import { investigateCluster } from "../api/investigations";
import { respondToCluster } from "../api/workflow";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api/client", () => {
  it("throws BackendUnavailableError (not a raw fetch TypeError) on network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiGet("/health")).rejects.toBeInstanceOf(BackendUnavailableError);
  });

  it("throws ApiError with the backend's error message on a 200-with-error-body response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ error: "No candidate cluster with id 'x'." }),
      })
    );
    await expect(apiGet("/risk/clusters/x")).rejects.toBeInstanceOf(ApiError);
  });

  it("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: "ok" }) })
    );
    const result = await apiGet("/health");
    expect(result).toEqual({ status: "ok" });
  });

  it("apiPost sends a JSON body and POST method", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", fetchMock);
    await apiPost("/agent/investigate/cc-1");
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/agent/investigate/cc-1`,
      expect.objectContaining({ method: "POST" })
    );
  });
});

describe("investigateCluster / respondToCluster call the correct endpoints", () => {
  it("investigateCluster POSTs to /agent/investigate/{cluster_id}", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    await investigateCluster("cc-0046");
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/agent/investigate/cc-0046`,
      expect.objectContaining({ method: "POST" })
    );
  });

  it("respondToCluster POSTs to /agent/respond/{cluster_id}", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    await respondToCluster("cc-0046");
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/agent/respond/cc-0046`,
      expect.objectContaining({ method: "POST" })
    );
  });
});
