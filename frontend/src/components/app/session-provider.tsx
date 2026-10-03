"use client";

import { createContext, useContext, useEffect } from "react";

import { api } from "@/lib/api";
import { useApiQuery } from "@/lib/hooks";
import type { SessionResponse, SessionUser } from "@/lib/types";

interface SessionContextValue {
  user: SessionUser | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

const SessionContext = createContext<SessionContextValue>({
  user: null,
  loading: true,
  error: null,
  refetch: () => undefined,
});

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { data, error, loading, refetch } = useApiQuery<SessionResponse>(
    "/api/v1/auth/session",
  );

  useEffect(() => {
    if (data?.user?.id) {
      api.setCacheScope(data.user.id);
    } else if (!loading && !data?.user) {
      api.clearPrivateCache();
      api.setCacheScope(null);
    }
  }, [data?.user, loading]);

  return (
    <SessionContext.Provider
      value={{
        user: data?.user ?? null,
        loading,
        error: error?.message ?? null,
        refetch,
      }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  return useContext(SessionContext);
}
