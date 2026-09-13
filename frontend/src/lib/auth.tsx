/** Authentication context.
 *
 *  Holds three states, not two. "Loading" is distinct from "signed out" because
 *  on a page reload we hold a refresh token but no access token yet — treating
 *  that as signed out would bounce the user to the login screen on every
 *  refresh, then bounce them back once the exchange completed.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, restoreSession } from "@/lib/api";
import {
  clearTokens,
  getRefreshToken,
  hasStoredSession,
  setTokens,
} from "@/lib/tokens";
import type { CurrentUser, Role, TokenResponse } from "@/lib/types";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  user: CurrentUser | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(() =>
    hasStoredSession() ? "loading" : "anonymous",
  );
  const [user, setUser] = useState<CurrentUser | null>(null);

  // On mount, exchange a stored refresh token for an access token and load the
  // profile. Runs once; the guard prevents a late response from a previous
  // session overwriting a newer one.
  useEffect(() => {
    let cancelled = false;

    if (!hasStoredSession()) {
      setStatus("anonymous");
      return;
    }

    void (async () => {
      const restored = await restoreSession();
      if (cancelled) return;

      if (!restored) {
        setStatus("anonymous");
        return;
      }

      try {
        const profile = await api.get<CurrentUser>("/auth/me");
        if (cancelled) return;
        setUser(profile);
        setStatus("authenticated");
      } catch {
        if (cancelled) return;
        clearTokens();
        setStatus("anonymous");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const tokens = await api.postAnonymous<TokenResponse>("/auth/login", {
      email,
      password,
    });
    setTokens(tokens.access_token, tokens.refresh_token);

    const profile = await api.get<CurrentUser>("/auth/me");
    setUser(profile);
    setStatus("authenticated");
  }, []);

  const signOut = useCallback(async () => {
    const refresh = getRefreshToken();
    if (refresh) {
      try {
        await api.post<void>("/auth/logout", { refresh_token: refresh });
      } catch {
        /* best effort */
      }
    }
    clearTokens();
    setUser(null);
    setStatus("anonymous");
  }, []);

  const hasRole = useCallback(
    (...roles: Role[]) => (user ? roles.includes(user.role) : false),
    [user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, signIn, signOut, hasRole }),
    [status, user, signIn, signOut, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
