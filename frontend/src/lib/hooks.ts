"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, apiRequest } from "@/lib/api";

interface QueryState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
}

export function useApiQuery<T>(
  path: string | null,
  options: { skip?: boolean } = {},
) {
  const [state, setState] = useState<QueryState<T>>({
    data: null,
    error: null,
    loading: Boolean(path) && !options.skip,
  });
  const [reloadKey, setReloadKey] = useState(0);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    if (!path || options.skip) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    const controller = new AbortController();
    setState((prev) => ({ ...prev, loading: true, error: null }));

    apiRequest<T>(path, { method: "GET", signal: controller.signal })
      .then((data) => {
        if (!alive.current) return;
        setState({ data, error: null, loading: false });
      })
      .catch((error: unknown) => {
        if (!alive.current || controller.signal.aborted) return;
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError(0, "unknown", "Beklenmeyen bir hata oluştu.");
        setState({ data: null, error: apiError, loading: false });
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, options.skip, reloadKey]);

  const refetch = useCallback(() => setReloadKey((key) => key + 1), []);

  return { ...state, refetch, setData: (data: T) => setState({ data, error: null, loading: false }) };
}

export function useMounted() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}
