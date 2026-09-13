import { useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import {
  Building2,
  ClipboardList,
  FileText,
  Home,
  Lock,
  Menu,
  Scale,
  User,
  X,
} from "lucide-react";

import logoImg from "@/assets/logo.png";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

/** Floating navigation.
 *
 *  Items are filtered by role. Hiding a link is presentation, not security — the
 *  backend enforces access independently — but showing an inspector-only screen
 *  to an employer just to have them receive a 403 is a worse experience than not
 *  offering it.
 */

interface NavItem {
  to: string;
  label: string;
  icon: typeof Home;
  exact?: boolean;
  /** Roles that see this item. Omitted means everyone, including visitors. */
  roles?: Role[];
}

const NAV: NavItem[] = [
  { to: "/", label: "Home", icon: Home, exact: true },
  { to: "/documents", label: "Documents", icon: FileText },
  {
    to: "/establishments",
    label: "Establishments",
    icon: Building2,
    roles: ["EMPLOYER", "INSPECTOR", "ADMIN", "ANALYST"],
  },
  {
    to: "/worklist",
    label: "Worklist",
    icon: ClipboardList,
    roles: ["INSPECTOR", "ADMIN", "ANALYST"],
  },
  { to: "/rules", label: "Rules", icon: Scale },
  { to: "/profile", label: "Profile", icon: User },
];

export function Navbar() {
  const location = useLocation();
  const { user } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const visible = NAV.filter((item) => {
    if (!item.roles) return true;
    return user ? item.roles.includes(user.role) : false;
  });

  function isActive(item: NavItem): boolean {
    return item.exact
      ? location.pathname === item.to
      : location.pathname.startsWith(item.to);
  }

  return (
    <>
      {/* Identity, top-left. Fixed branding. */}
      <div className="pointer-events-auto fixed left-4 top-3.5 z-50 sm:left-7">
        <Link
          to="/"
          className="group flex items-center gap-3.5 transition-transform duration-200 hover:scale-[1.01] focus:outline-none"
          title="Shram Drishti · Ministry of Labour & Employment, Government of India"
        >
          <img
            src={logoImg}
            alt="Shram Drishti — Ministry of Labour & Employment, Government of India"
            className="h-16 w-auto object-contain drop-shadow-md transition-transform duration-200 group-hover:scale-105 sm:h-20"
          />
          <div className="flex flex-col justify-center">
            <span className="text-xl font-black leading-none tracking-tight text-slate-900 sm:text-2xl">
              Shram Drishti
            </span>
            <span className="mt-1 text-xs font-bold leading-tight tracking-tight text-slate-700 sm:text-sm">
              Ministry of Labour &amp; Employment
            </span>
            <span className="text-[10px] font-semibold uppercase leading-tight tracking-wider text-slate-500 sm:text-xs">
              Government of India
            </span>
          </div>
        </Link>
      </div>

      {/* Centred capsule */}
      <header className="pointer-events-none fixed left-1/2 top-4 z-50 hidden -translate-x-1/2 xl:block">
        <nav
          aria-label="Main"
          className="pointer-events-auto flex items-center gap-1.5 rounded-full border border-sky-200/90 bg-white/95 px-4 py-2.5 text-slate-900 shadow-[0_10px_35px_rgba(56,189,248,0.16)] backdrop-blur-2xl transition-all duration-300 hover:border-sky-300 hover:bg-white"
        >
          {visible.map((item) => {
            const active = isActive(item);
            const Icon = item.icon;

            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={Boolean(item.exact)}
                aria-current={active ? "page" : undefined}
                className={[
                  "flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-bold tracking-tight transition-all duration-200 lg:text-[15px]",
                  active
                    ? "scale-[1.02] bg-slate-900 text-white shadow-md"
                    : "text-slate-600 hover:scale-[1.01] hover:bg-sky-50/90 hover:text-slate-950",
                ].join(" ")}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
                {item.to === "/documents" && !user && (
                  <Lock className="h-3 w-3 text-amber-500 shrink-0 ml-0.5" />
                )}
              </NavLink>
            );
          })}
        </nav>
      </header>

      {/* Mobile */}
      <div className="pointer-events-auto fixed right-4 top-4 z-50 sm:right-7 xl:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen((open) => !open)}
          aria-expanded={mobileOpen}
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
          className="flex h-12 w-12 cursor-pointer items-center justify-center rounded-full border border-sky-200/90 bg-white/95 text-slate-700 shadow-[0_6px_25px_rgba(56,189,248,0.14)] backdrop-blur-2xl transition-colors hover:border-sky-300 hover:text-slate-950"
        >
          {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>

        {mobileOpen && (
          <nav
            aria-label="Main"
            className="absolute right-0 top-14 flex w-72 flex-col gap-1.5 rounded-3xl border border-sky-200/90 bg-white/98 p-4 shadow-2xl backdrop-blur-2xl"
          >
            {visible.map((item) => {
              const active = isActive(item);
              const Icon = item.icon;

              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={Boolean(item.exact)}
                  onClick={() => setMobileOpen(false)}
                  aria-current={active ? "page" : undefined}
                  className={[
                    "flex items-center gap-3.5 rounded-2xl px-5 py-3 text-base font-bold transition-colors",
                    active
                      ? "bg-slate-900 text-white shadow-sm"
                      : "text-slate-700 hover:bg-sky-50 hover:text-slate-950",
                  ].join(" ")}
                >
                  <Icon className="h-5 w-5 text-sky-600" />
                  <span>{item.label}</span>
                  {item.to === "/documents" && !user && (
                    <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-bold text-amber-700">
                      <Lock className="h-3 w-3" />
                      Locked
                    </span>
                  )}
                </NavLink>
              );
            })}
          </nav>
        )}
      </div>
    </>
  );
}
