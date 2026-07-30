import type { ReactNode } from "react";

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div style={{ fontSize: "1.05rem", marginBottom: "0.4rem" }}>{title}</div>
      {hint && <div className="small" style={{ marginBottom: "0.9rem" }}>{hint}</div>}
      {action}
    </div>
  );
}

/** Shown when a query errored because the backend is down/unreachable. */
export function BackendDown({ message }: { message?: string }) {
  return (
    <div className="empty">
      <div style={{ fontSize: "1.05rem", marginBottom: "0.4rem" }}>Backend unavailable</div>
      <div className="small muted">
        Could not reach the API. Start the backend (<span className="mono">docker compose up</span>) — this
        view will populate automatically.
      </div>
      {message && <div className="small muted mono" style={{ marginTop: "0.5rem" }}>{message}</div>}
    </div>
  );
}
