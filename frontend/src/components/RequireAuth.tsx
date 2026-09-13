import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

interface RequireAuthProps {
  children: ReactNode;
  /** When set, the user must hold one of these roles. */
  roles?: Role[];
}

export function RequireAuth({ children, roles }: RequireAuthProps) {
  const { status, user } = useAuth();
  const location = useLocation();

  // Distinct from "anonymous": we may be mid token-exchange on a page reload.
  // Redirecting here would bounce the user to login on every refresh.
  if (status === "loading") {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex min-h-dvh items-center justify-center text-sm text-slate-500"
      >
        <span
          aria-hidden="true"
          className="mr-2 size-4 animate-spin rounded-full border-2 border-slate-400 border-t-transparent"
        />
        Restoring your session&hellip;
      </div>
    );
  }

  if (status === "anonymous") {
    // Sign-in lives on the Profile page rather than a separate screen, so an
    // unauthenticated visitor lands somewhere that explains who this is for and
    // lets them sign in without losing where they were headed.
    return <Navigate to="/profile" replace state={{ from: location.pathname }} />;
  }

  if (roles && user && !roles.includes(user.role)) {
    // Sent to the overview rather than shown a 403 page: the user is legitimate,
    // they simply took a link meant for another role.
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
