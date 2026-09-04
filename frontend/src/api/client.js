/**
 * Centralized API client. Every backend call in the app goes through
 * `apiGet` / `apiPost` here -- components never call `fetch()` directly.
 *
 * Base URL comes from VITE_API_BASE_URL (see .env.example). No secrets
 * live here or anywhere in frontend code: the backend holds
 * GEMINI_API_KEY, database credentials, etc. -- the browser only ever
 * sees this one public API base URL.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(message, { status, url } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.url = url;
  }
}

/** Network-level failure (backend unreachable) vs. an HTTP error response. */
export class BackendUnavailableError extends ApiError {
  constructor(url) {
    super("TrustGraph backend unavailable", { url });
    this.name = "BackendUnavailableError";
  }
}

async function request(path, options = {}) {
  const url = `${API_BASE_URL}${path}`;
  let response;
  try {
    response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    // fetch() throws TypeError on network failure / CORS / backend down --
    // this is exactly the "backend unavailable" state the UI must show
    // instead of a blank screen or an unhandled console error.
    throw new BackendUnavailableError(url);
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    // non-JSON body -- fall through, body stays null
  }

  if (!response.ok) {
    throw new ApiError(body?.detail || body?.error || `Request failed (${response.status})`, {
      status: response.status,
      url,
    });
  }

  // The backend's read-only endpoints return {"error": "..."} with a
  // 200 status for "not found" cases (see backend/app/main.py) rather
  // than a 404 -- surface that consistently as an ApiError too, so
  // every caller has one error path to handle.
  if (body && typeof body === "object" && "error" in body && Object.keys(body).length === 1) {
    throw new ApiError(body.error, { status: response.status, url });
  }

  return body;
}

export function apiGet(path) {
  return request(path, { method: "GET" });
}

export function apiPost(path, payload) {
  return request(path, {
    method: "POST",
    body: payload !== undefined ? JSON.stringify(payload) : undefined,
  });
}

export { API_BASE_URL };
