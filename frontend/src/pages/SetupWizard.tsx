import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { setupApi } from "@/api/client";
import { useSetupStatus, qk } from "@/api/queries";
import type { KeyTestResult } from "@/api/types";

// First-run setup for the single approved workflow. Three things to configure:
// Keys (Anthropic + Google Thai TTS) → Video (LTX-2.5 on Modal) → TikTok posting.
// Each field is written straight to .env via /api/setup/save; "Test" does a live
// auth call via /api/setup/test/{provider}.
const STEPS = ["Keys", "Video", "TikTok", "Finish"] as const;

type TestState = KeyTestResult | "testing" | undefined;

interface Field {
  env: string;
  label: string;
  placeholder?: string;
  type?: "text" | "password" | "select";
  options?: string[];
  help?: string;
}

export function SetupWizard() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const status = useSetupStatus();
  const [step, setStep] = useState(0);
  const [jumped, setJumped] = useState(false);

  // Open directly on the first UNFILLED step (keys → video → tiktok) so a missing
  // API drops the operator straight onto the screen they need to fill in.
  useEffect(() => {
    if (jumped || !status.data?.steps) return;
    const order: Array<keyof typeof status.data.steps> = ["keys", "video", "tiktok"];
    const first = order.findIndex((k) => !status.data!.steps[k]);
    setStep(first === -1 ? 0 : first);
    setJumped(true);
  }, [status.data, jumped]);

  function next() {
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
    qc.invalidateQueries({ queryKey: qk.setupStatus });
  }
  function back() {
    setStep((s) => Math.max(s - 1, 0));
  }

  async function finish() {
    // Flip the app into the real stack and mark first-run complete.
    await setupApi.save({ DRY_RUN: "false" }).catch(() => {});
    await setupApi.complete().catch(() => {});
    await qc.invalidateQueries({ queryKey: qk.setupStatus });
    nav("/");
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="brand">AutoUGC-TH · First-run setup</span>
        <div className="grow" />
        <span className="chip">{step + 1}/{STEPS.length}</span>
      </header>
      <main className="app-main" style={{ maxWidth: "48rem", margin: "0 auto", width: "100%" }}>
        <div className="wizard-rail">
          {STEPS.map((label, i) => (
            <div key={label} className={`rail-step ${i < step ? "done" : i === step ? "current" : ""}`}>
              <span className="rail-dot">{i < step ? "✓" : i + 1}</span>
              {label}
              {i < STEPS.length - 1 && <span className="muted">—</span>}
            </div>
          ))}
        </div>

        {step === 0 && (
          <ProviderStep
            title="Connect your keys"
            blurb="Anthropic writes the Thai script; Google Cloud TTS speaks it; SocialCrawl looks up the product on TikTok Shop TH (title, image, THB price). Keys already set are kept — just fill any that are missing."
            fields={[
              { env: "ANTHROPIC_API_KEY", label: "Anthropic API key", type: "password", placeholder: "sk-ant-…" },
              { env: "GOOGLE_TTS_API_KEY", label: "Google Cloud TTS key", type: "password", placeholder: "AIza…" },
              { env: "SOCIALCRAWL_API_KEY", label: "SocialCrawl key", type: "password", placeholder: "sc-…" },
            ]}
            tests={[
              { provider: "llm", label: "Anthropic", env: "ANTHROPIC_API_KEY" },
              { provider: "tts", label: "Google TTS", env: "GOOGLE_TTS_API_KEY" },
              { provider: "scraper", label: "SocialCrawl", env: "SOCIALCRAWL_API_KEY" },
            ]}
            configured={status.data?.configured}
            onNext={next}
          />
        )}
        {step === 1 && (
          <ProviderStep
            title="Video engine — LTX-2.5 on Modal"
            blurb="Deploy once with `modal deploy deploy/modal_ltx.py`, then paste the URL it prints. Generation scales to zero between renders (~$0/mo inside Modal's free credit)."
            fields={[
              { env: "MODAL_LTX_URL", label: "Modal web URL", placeholder: "https://…modal.run" },
              { env: "MODAL_LTX_TOKEN", label: "Shared token", type: "password", placeholder: "matches AUTOUGC_LTX_TOKEN" },
            ]}
            tests={[{ provider: "video", label: "Modal /health", env: "MODAL_LTX_URL" }]}
            configured={status.data?.configured}
            onNext={next}
            onBack={back}
          />
        )}
        {step === 2 && (
          <ProviderStep
            title="Connect TikTok"
            blurb="Paste a Content Posting API access token. 'inbox' mode uploads to your drafts (works before app audit); 'direct' posts to the profile once your app is audited. AI-label is applied automatically."
            fields={[
              { env: "TIKTOK_ACCESS_TOKEN", label: "Access token", type: "password", placeholder: "act.…" },
              { env: "TIKTOK_POSTING_MODE", label: "Mode", type: "select", options: ["direct", "inbox"] },
            ]}
            tests={[{ provider: "tiktok", label: "TikTok auth", env: "TIKTOK_ACCESS_TOKEN" }]}
            configured={status.data?.configured}
            optional
            onNext={next}
            onBack={back}
          />
        )}
        {step === 3 && <FinishStep steps={status.data?.steps} onBack={back} onFinish={finish} />}
      </main>
    </div>
  );
}

// A generic "save these fields, then test these providers" step.
function ProviderStep({
  title, blurb, fields, tests, configured, optional, onNext, onBack,
}: {
  title: string;
  blurb: string;
  fields: Field[];
  tests: { provider: string; label: string; env?: string }[];
  configured?: Record<string, boolean>;
  optional?: boolean;
  onNext: () => void;
  onBack?: () => void;
}) {
  const isSet = (env?: string) => !!(env && configured?.[env]);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.env, f.type === "select" ? (f.options?.[0] ?? "") : ""])),
  );
  const [results, setResults] = useState<Record<string, TestState>>({});
  const [saving, setSaving] = useState(false);

  async function saveAndTest() {
    setSaving(true);
    try {
      // Only send non-empty values so a blank "already set" field is never wiped.
      const payload = Object.fromEntries(
        Object.entries(values).filter(([, v]) => v.trim() !== ""),
      );
      await setupApi.save(payload);
      for (const t of tests) setResults((r) => ({ ...r, [t.provider]: "testing" }));
      for (const t of tests) {
        try {
          const res = await setupApi.testKey(t.provider);
          setResults((r) => ({ ...r, [t.provider]: res }));
        } catch (e) {
          setResults((r) => ({ ...r, [t.provider]: { ok: false, error: (e as Error).message } }));
        }
      }
    } finally {
      setSaving(false);
    }
  }

  // A provider is satisfied if it just tested green OR it was already configured.
  const allGreen = tests.every((t) => {
    const r = results[t.provider];
    return (r && r !== "testing" && r.ok) || isSet(t.env);
  });

  return (
    <div className="card stack">
      <strong>{title}</strong>
      <p className="small muted">{blurb}</p>

      {fields.map((f) => {
        const set = isSet(f.env);
        return (
        <div key={f.env} className="row" style={{ gap: "0.6rem" }}>
          <span style={{ width: "12rem" }}>
            {f.label}
            {set && <span className="small" style={{ color: "var(--green)" }}> ✓ set</span>}
          </span>
          {f.type === "select" ? (
            <select className="grow" value={values[f.env] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [f.env]: e.target.value }))}>
              {(f.options ?? []).map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
          ) : (
            <input
              type={f.type === "password" ? "password" : "text"}
              className="grow"
              placeholder={set ? "leave blank to keep current" : (f.placeholder ?? "")}
              value={values[f.env] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.env]: e.target.value }))}
            />
          )}
        </div>
        );
      })}

      <div className="row" style={{ gap: "0.6rem", marginTop: "0.3rem" }}>
        <button className="small" onClick={saveAndTest} disabled={saving}>
          {saving ? "Saving…" : "Save & test"}
        </button>
        {tests.map((t) => {
          const r = results[t.provider];
          const set = isSet(t.env);
          const cls = r && r !== "testing" ? (r.ok ? "ok" : "bad") : set ? "ok" : "idle";
          const text = r === "testing"
            ? "…"
            : r
              ? (r.ok ? `ok ${r.latency_ms ?? "?"}ms` : r.error || "fail")
              : set ? "configured" : "—";
          return (
            <span key={t.provider} className="row" style={{ gap: "0.3rem" }}>
              <span className={`dot ${cls}`} />
              <span className="small muted">{t.label}: {text}</span>
            </span>
          );
        })}
      </div>

      <NavButtons
        onNext={onNext}
        onBack={onBack}
        nextDisabled={!allGreen && !optional}
        nextLabel={!allGreen && optional ? "Skip for now →" : "Next →"}
      />
    </div>
  );
}

function NavButtons({ onNext, onBack, nextLabel = "Next →", nextDisabled }: { onNext: () => void; onBack?: () => void; nextLabel?: string; nextDisabled?: boolean }) {
  return (
    <div className="row spread" style={{ marginTop: "1.25rem" }}>
      {onBack ? <button className="ghost" onClick={onBack}>Back</button> : <span />}
      <button className="primary" onClick={onNext} disabled={nextDisabled}>{nextLabel}</button>
    </div>
  );
}

function FinishStep({ steps, onBack, onFinish }: { steps?: Record<string, boolean>; onBack: () => void; onFinish: () => void }) {
  const rows = [
    ["Keys (Anthropic + Google TTS + SocialCrawl)", steps?.keys],
    ["Video (LTX-2.5 on Modal)", steps?.video],
    ["TikTok posting", steps?.tiktok],
  ] as const;
  return (
    <div className="card stack">
      <strong>Review + finish</strong>
      {rows.map(([label, ok]) => (
        <div key={label} className="row spread" style={{ borderBottom: "1px solid var(--border)", paddingBottom: "0.4rem" }}>
          <span>{label}</span>
          <span className={ok ? "check-ok" : "muted"}>{ok ? "✓ configured" : "— not set"}</span>
        </div>
      ))}
      <p className="small muted">Finishing turns off DRY_RUN (the app starts using your real keys) and opens the dashboard. You can paste a product URL to make your first video.</p>
      <div className="row spread">
        <button className="ghost" onClick={onBack}>Back</button>
        <button className="success" onClick={onFinish}>Finish setup</button>
      </div>
    </div>
  );
}
