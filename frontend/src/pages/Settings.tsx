import { useEffect, useState } from "react";
import {
  useAddClaim,
  useBudget,
  useClaims,
  useCompliance,
  useDeleteClaim,
  useProviders,
  useSaveBudget,
  useSaveCompliance,
} from "@/api/queries";
import { setupApi } from "@/api/client";
import { useUiStore } from "@/store/uiStore";
import type { BudgetSettings, ComplianceSettings } from "@/api/types";

// Screen 7 (§7A.7): tabbed settings — Providers / Budget / Compliance / Approved-claims / Seeds / Account.
const TABS = ["Providers", "Budget", "Compliance", "Claims", "Seeds", "Account"] as const;
type Tab = (typeof TABS)[number];

export function Settings() {
  const [tab, setTab] = useState<Tab>("Providers");
  return (
    <div>
      <h1 className="page-title">Settings</h1>
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>
      {tab === "Providers" && <ProvidersTab />}
      {tab === "Budget" && <BudgetTab />}
      {tab === "Compliance" && <ComplianceTab />}
      {tab === "Claims" && <ClaimsTab />}
      {tab === "Seeds" && <SeedsTab />}
      {tab === "Account" && <AccountTab />}
    </div>
  );
}

function ProvidersTab() {
  const providers = useProviders();
  const [testing, setTesting] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { ok: boolean; latency?: number; error?: string }>>({});
  const keyNames = ["heygen", "elevenlabs", "fal", "scraper", "postpeer", "llm"];

  async function test(p: string) {
    setTesting(p);
    try {
      const r = await setupApi.testKey(p);
      setResults((s) => ({ ...s, [p]: { ok: r.ok, latency: r.latency_ms, error: r.error } }));
    } catch (e) {
      setResults((s) => ({ ...s, [p]: { ok: false, error: (e as Error).message } }));
    } finally {
      setTesting(null);
    }
  }

  return (
    <div className="card stack">
      <div className="row spread">
        <strong>Providers</strong>
        <span className="chip">scraper: {providers.data?.scraper ?? "—"}</span>
      </div>
      <p className="small muted">Rotate keys and re-test. Avatar/voice can be re-created in the setup wizard.</p>
      {keyNames.map((p) => {
        const r = results[p];
        return (
          <div key={p} className="row" style={{ gap: "0.75rem" }}>
            <span style={{ width: "6rem", textTransform: "capitalize" }}>{p}</span>
            <input type="password" placeholder="•••••••• (leave blank to keep)" className="grow" onChange={() => {}} />
            <button className="small" onClick={() => test(p)} disabled={testing === p}>
              {testing === p ? "…" : "Test"}
            </button>
            <span className="row" style={{ gap: "0.3rem", width: "6rem" }}>
              <span className={`dot ${r ? (r.ok ? "ok" : "bad") : "idle"}`} />
              <span className="small muted">{r ? (r.ok ? `${r.latency ?? "?"}ms` : r.error || "fail") : "untested"}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

function BudgetTab() {
  const budget = useBudget();
  const save = useSaveBudget();
  const setToast = useUiStore((s) => s.setToast);
  const [form, setForm] = useState<BudgetSettings>({
    per_video_usd: 5,
    daily_cap_usd: 50,
    monthly_cap_usd: 150,
    on_breach: "pause",
  });
  useEffect(() => {
    if (budget.data) setForm(budget.data);
  }, [budget.data]);

  return (
    <div className="card stack" style={{ maxWidth: "28rem" }}>
      <strong>Cost guard</strong>
      <div>
        <label>Per-video soft cap ($)</label>
        <input type="number" step="0.5" value={form.per_video_usd} onChange={(e) => setForm({ ...form, per_video_usd: +e.target.value })} />
      </div>
      <div>
        <label>Daily hard cap ($)</label>
        <input type="number" value={form.daily_cap_usd} onChange={(e) => setForm({ ...form, daily_cap_usd: +e.target.value })} />
      </div>
      <div>
        <label>Monthly hard cap ($)</label>
        <input type="number" value={form.monthly_cap_usd} onChange={(e) => setForm({ ...form, monthly_cap_usd: +e.target.value })} />
      </div>
      <div>
        <label>On breach</label>
        <select value={form.on_breach} onChange={(e) => setForm({ ...form, on_breach: e.target.value as "pause" | "warn" })}>
          <option value="pause">Pause the queue</option>
          <option value="warn">Warn only</option>
        </select>
      </div>
      <button
        className="primary"
        disabled={save.isPending}
        onClick={() => save.mutateAsync(form).then(() => setToast({ kind: "success", message: "Budget saved" })).catch(() => setToast({ kind: "error", message: "Save failed" }))}
      >
        Save
      </button>
    </div>
  );
}

function ComplianceTab() {
  const compliance = useCompliance();
  const save = useSaveCompliance();
  const setToast = useUiStore((s) => s.setToast);
  const [form, setForm] = useState<ComplianceSettings>({
    disclosure_text: "#โฆษณา",
    disclosure_hashtags: ["#โฆษณา", "#ad"],
    restricted_keywords: [],
    strictness: "high",
    reroll_auto_fixes_claims: true,
  });
  useEffect(() => {
    if (compliance.data) setForm(compliance.data);
  }, [compliance.data]);

  return (
    <div className="card stack" style={{ maxWidth: "34rem" }}>
      <strong>Compliance defaults</strong>
      <div>
        <label>Required disclosure text / hashtag</label>
        <input value={form.disclosure_text} onChange={(e) => setForm({ ...form, disclosure_text: e.target.value })} lang="th" />
      </div>
      <div>
        <label>Disclosure hashtags (comma-separated)</label>
        <input
          value={form.disclosure_hashtags.join(", ")}
          onChange={(e) => setForm({ ...form, disclosure_hashtags: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
        />
      </div>
      <div>
        <label>Restricted keywords (comma-separated)</label>
        <textarea
          rows={2}
          value={form.restricted_keywords.join(", ")}
          onChange={(e) => setForm({ ...form, restricted_keywords: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
        />
      </div>
      <div>
        <label>Strictness</label>
        <select value={form.strictness} onChange={(e) => setForm({ ...form, strictness: e.target.value as ComplianceSettings["strictness"] })}>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
      </div>
      <label className="row" style={{ gap: "0.5rem", cursor: "pointer" }}>
        <input type="checkbox" style={{ width: "auto" }} checked={form.reroll_auto_fixes_claims} onChange={(e) => setForm({ ...form, reroll_auto_fixes_claims: e.target.checked })} />
        <span>Re-roll auto-fixes flagged claims</span>
      </label>
      <button
        className="primary"
        disabled={save.isPending}
        onClick={() => save.mutateAsync(form).then(() => setToast({ kind: "success", message: "Compliance saved" })).catch(() => setToast({ kind: "error", message: "Save failed" }))}
      >
        Save
      </button>
    </div>
  );
}

function ClaimsTab() {
  const claims = useClaims();
  const add = useAddClaim();
  const del = useDeleteClaim();
  const [th, setTh] = useState("");
  const [en, setEn] = useState("");
  const [note, setNote] = useState("");

  return (
    <div className="stack" style={{ maxWidth: "40rem" }}>
      <div className="card stack">
        <strong>Add approved claim</strong>
        <p className="small muted">The whitelist §6 checks every script against. Only claims here can appear on a post.</p>
        <div>
          <label>Claim (Thai)</label>
          <input value={th} onChange={(e) => setTh(e.target.value)} lang="th" />
        </div>
        <div>
          <label>Claim (English)</label>
          <input value={en} onChange={(e) => setEn(e.target.value)} />
        </div>
        <div>
          <label>Evidence note (optional)</label>
          <input value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <button
          className="primary"
          disabled={!th.trim() || add.isPending}
          onClick={() =>
            add.mutateAsync({ claim_th: th, claim_en: en, evidence_note: note }).then(() => {
              setTh(""); setEn(""); setNote("");
            }).catch(() => {})
          }
        >
          Add claim
        </button>
      </div>

      <div className="card stack">
        <strong>Approved claims</strong>
        {claims.isLoading ? (
          <div className="small muted">Loading…</div>
        ) : !claims.data || claims.data.claims.length === 0 ? (
          <div className="small muted">No approved claims yet.</div>
        ) : (
          claims.data.claims.map((c) => (
            <div key={c.id} className="row spread" style={{ borderBottom: "1px solid var(--border)", paddingBottom: "0.4rem" }}>
              <div>
                <div lang="th">{c.claim_th}</div>
                {c.claim_en && <div className="small muted">{c.claim_en}</div>}
              </div>
              <button className="small danger" onClick={() => del.mutateAsync(c.id).catch(() => {})}>Delete</button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function SeedsTab() {
  return (
    <div className="card">
      <strong>Seed sets</strong>
      <p className="small muted">Edit the swipe-mining seed sets (TikTok handles / hashtags / sound IDs). Managed in the setup wizard's Seeds step; the same <span className="mono">POST /api/setup/seeds</span> endpoint backs both.</p>
    </div>
  );
}

function AccountTab() {
  return (
    <div className="card stack" style={{ maxWidth: "28rem" }}>
      <strong>Account</strong>
      <p className="small muted">Single-operator local app. Optional local password is set via the backend <span className="mono">APP_PASSWORD</span> env var.</p>
      <div className="row wrap">
        <button className="ghost">Export data</button>
        <button className="danger">Wipe local data</button>
      </div>
    </div>
  );
}
