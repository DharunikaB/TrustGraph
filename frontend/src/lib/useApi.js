import { useCallback, useEffect, useState } from "react";
import { BackendUnavailableError } from "../api/client";

/**
 * Fetches `fetcher()` on mount (and whenever `deps` change), exposing
 * {data, loading, error, isBackendUnavailable, reload}. Every page/panel
 * that reads from the API uses this instead of ad-hoc useEffect/fetch
 * logic, so loading/error handling stays consistent everywhere.
 */
export function useApiData(fetcher, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetcher()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => load(), [load]);

  return {
    data,
    loading,
    error,
    isBackendUnavailable: error instanceof BackendUnavailableError,
    reload: load,
  };
}

/**
 * For user-triggered actions (POST calls) rather than on-mount fetches:
 * exposes {run, loading, error, data} where `run()` is called explicitly
 * (e.g. from a button's onClick), never automatically.
 */
export function useApiAction(actionFn) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(
    async (...args) => {
      setLoading(true);
      setError(null);
      try {
        const result = await actionFn(...args);
        setData(result);
        return result;
      } catch (err) {
        setError(err);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [actionFn]
  );

  const reset = useCallback(() => {
    setData(null);
    setError(null);
  }, []);

  return { run, data, loading, error, reset };
}
