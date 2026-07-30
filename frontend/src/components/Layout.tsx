import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Header } from "./Header";
import { useUiStore } from "@/store/uiStore";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/new", label: "New Video" },
  { to: "/library", label: "Swipe Library" },
  { to: "/analytics", label: "Analytics" },
  { to: "/settings", label: "Settings" },
];

export function Layout({ children }: { children: ReactNode }) {
  const toast = useUiStore((s) => s.toast);
  const setToast = useUiStore((s) => s.setToast);

  return (
    <div className="app-shell">
      <Header />
      <div className="app-body">
        <nav className="app-nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <main className="app-main">{children}</main>
      </div>
      {toast && (
        <div className={`toast ${toast.kind}`} onClick={() => setToast(null)}>
          {toast.message}
        </div>
      )}
    </div>
  );
}
