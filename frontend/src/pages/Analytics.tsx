import { useAnalyticsVideos, useLeaderboard } from "@/api/queries";
import { BackendDown, EmptyState } from "@/components/EmptyState";
import { ApiError } from "@/api/client";
import { compactNum, money } from "@/lib/format";
import type { LeaderboardEntry } from "@/api/types";

// Screen 6 (§7A.6): winner dashboard — per-video performance, winner flags,
// and win-rate attribution leaderboards by hook/formula/pacing template.
export function Analytics() {
  const videos = useAnalyticsVideos();
  const board = useLeaderboard();

  const isBackendDown =
    videos.isError && videos.error instanceof ApiError && videos.error.status === 0;

  if (isBackendDown) {
    return (
      <div>
        <h1 className="page-title">Analytics</h1>
        <BackendDown />
      </div>
    );
  }

  const rows = [...(videos.data?.videos ?? [])].sort(
    (a, b) => (b.views_per_dollar ?? 0) - (a.views_per_dollar ?? 0),
  );

  return (
    <div>
      <h1 className="page-title">Analytics</h1>

      {videos.isLoading ? (
        <div className="empty">Loading…</div>
      ) : rows.length === 0 ? (
        <EmptyState title="No performance data yet" hint="Metrics populate after your posts go live." />
      ) : (
        <div className="card" style={{ padding: 0, overflowX: "auto", marginBottom: "1.5rem" }}>
          <table className="jobs">
            <thead>
              <tr>
                <th>Video</th>
                <th>Views</th>
                <th>Watch-thru</th>
                <th>Likes/Cmts/Shares</th>
                <th>Shop clicks/orders</th>
                <th>Cost</th>
                <th>Views/$</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((v) => (
                <tr key={v.id}>
                  <td>
                    {v.is_winner ? "★ " : ""}
                    {v.product || v.id}
                  </td>
                  <td>{compactNum(v.views)}</td>
                  <td>{v.full_video_watch_rate != null ? `${Math.round(v.full_video_watch_rate * 100)}%` : "—"}</td>
                  <td className="small">
                    {compactNum(v.likes)} / {compactNum(v.comments)} / {compactNum(v.shares)}
                  </td>
                  <td className="small">
                    {compactNum(v.product_clicks)} / {compactNum(v.orders)}
                  </td>
                  <td className="mono">{money(v.cost)}</td>
                  <td className="mono">{v.views_per_dollar != null ? compactNum(v.views_per_dollar) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 style={{ fontSize: "1.1rem" }}>Template leaderboards</h2>
      <div className="row wrap" style={{ alignItems: "flex-start", gap: "1rem" }}>
        <LeaderboardCard title="Hooks" entries={board.data?.hooks} loading={board.isLoading} />
        <LeaderboardCard title="Formulas" entries={board.data?.formulas} loading={board.isLoading} />
        <LeaderboardCard title="Pacing" entries={board.data?.pacing} loading={board.isLoading} />
      </div>
    </div>
  );
}

function LeaderboardCard({
  title,
  entries,
  loading,
}: {
  title: string;
  entries?: LeaderboardEntry[];
  loading: boolean;
}) {
  return (
    <div className="card grow stack" style={{ minWidth: "16rem" }}>
      <strong>{title}</strong>
      {loading ? (
        <div className="small muted">Loading…</div>
      ) : !entries || entries.length === 0 ? (
        <div className="small muted">No data yet.</div>
      ) : (
        entries.map((e) => (
          <div key={e.template_id}>
            <div className="row spread small">
              <span lang="th">{e.label}</span>
              <span className="muted">{Math.round(e.win_rate * 100)}%</span>
            </div>
            <div className="bar"><span style={{ width: `${Math.min(100, e.win_rate * 100)}%` }} /></div>
          </div>
        ))
      )}
    </div>
  );
}
