import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLibrary, useRefreshMining } from "@/api/queries";
import { BackendDown, EmptyState } from "@/components/EmptyState";
import { ApiError } from "@/api/client";
import { compactNum } from "@/lib/format";
import type { SwipeVideo, Template, TemplateType } from "@/api/types";

// Screen 5 (§7A.5): mined top videos + extracted Formula/Hook/Pacing templates,
// with the mandatory engagement-proxy caveat and a "use this in next video" affordance.
export function Library() {
  const nav = useNavigate();
  const [seed, setSeed] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<TemplateType | "">("");
  const [selected, setSelected] = useState<SwipeVideo | null>(null);
  const libQuery = useLibrary(seed || undefined, typeFilter || undefined);
  const refresh = useRefreshMining();

  const data = libQuery.data;
  const isBackendDown =
    libQuery.isError && libQuery.error instanceof ApiError && libQuery.error.status === 0;

  // "use this template" seeds the New Video flow (§7A.5).
  function useTemplate(t: Template) {
    nav(`/new?template=${t.id}&type=${t.type}`);
  }

  return (
    <div>
      <h1 className="page-title">Swipe Library</h1>

      {/* Persistent caveat banner — §2 honesty requirement. */}
      <div className="caveat-banner">
        ⚠ Engagement figures are <strong>proxies</strong> scraped from public data, not verified
        analytics. Use as a directional signal only.
      </div>

      <div className="row wrap" style={{ marginBottom: "1rem" }}>
        <select style={{ width: "auto" }} value={seed} onChange={(e) => setSeed(e.target.value)}>
          <option value="">All seed sets</option>
          <option value="TH-Beauty-Top">TH-Beauty-Top</option>
          <option value="TH-Gadget-Top">TH-Gadget-Top</option>
        </select>
        <select style={{ width: "auto" }} value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as TemplateType | "")}>
          <option value="">All template types</option>
          <option value="hook">Hook</option>
          <option value="formula">Formula</option>
          <option value="pacing">Pacing</option>
        </select>
        <div className="grow" />
        <button onClick={() => refresh.mutateAsync(seed || undefined).catch(() => {})} disabled={refresh.isPending}>
          ↻ {refresh.isPending ? "Mining…" : "Mine"}
        </button>
      </div>

      {isBackendDown ? (
        <BackendDown />
      ) : libQuery.isLoading ? (
        <div className="empty">Loading library…</div>
      ) : !data || data.videos.length === 0 ? (
        <EmptyState title="No mined videos yet" hint="Add seed accounts in Settings, then hit Mine." />
      ) : (
        <>
          <div className="mined-grid">
            {data.videos.map((v) => (
              <div key={v.id} className="mined-card" onClick={() => setSelected(v)}>
                <div className="mined-thumb">
                  {v.thumbnail_url ? (
                    <img src={v.thumbnail_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  ) : (
                    "▶"
                  )}
                </div>
                <div style={{ padding: "0.5rem" }}>
                  <div className="small">▶ {compactNum(v.views)}</div>
                  <div className="small muted">{v.source_handle || "—"}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Detail drawer with extracted templates */}
          {selected && (
            <div className="card stack" style={{ marginTop: "1.25rem" }}>
              <div className="row spread">
                <strong>Detail · {selected.source_handle || selected.id}</strong>
                <button className="ghost small" onClick={() => setSelected(null)}>✕</button>
              </div>
              <div className="row wrap small muted">
                <span>▶ {compactNum(selected.views)} views</span>
                <span>♥ {compactNum(selected.likes)}</span>
                <span>💬 {compactNum(selected.comments)}</span>
                <span>↗ {compactNum(selected.shares)}</span>
                <span className="chip">signal: {selected.signal_type || "engagement_proxy"}</span>
              </div>
              <div className="stack">
                {data.templates
                  .filter((t) => !selected.seed_set || t) // templates are seed-scoped by the API
                  .map((t) => (
                    <div key={t.id} className="row spread">
                      <div>
                        <span className="chip" style={{ marginRight: "0.5rem" }}>{t.type}</span>
                        <span lang="th">{t.label}</span>
                        {t.summary && <span className="muted small"> — {t.summary}</span>}
                      </div>
                      <button className="small" onClick={() => useTemplate(t)}>use →</button>
                    </div>
                  ))}
                {data.templates.length === 0 && <div className="small muted">No templates extracted yet.</div>}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
