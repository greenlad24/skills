import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { setupApi } from "@/api/client";
import { useSetupStatus, qk } from "@/api/queries";
import type { KeyTestResult, SeedSet } from "@/api/types";

// Screen 1 (§7A.1): first-run setup wizard. 6 linear steps with a progress rail; each step
// persists on completion (resumable). Backed by the /api/setup/* endpoints.
const STEPS = ["Keys", "Avatar+Voice", "Consent", "TikTok", "Seeds", "Review"] as const;

export function SetupWizard() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const status = useSetupStatus();
  const [step, setStep] = useState(0);

  function next() {
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
    qc.invalidateQueries({ queryKey: qk.setupStatus });
  }
  function back() {
    setStep((s) => Math.max(s - 1, 0));
  }

  async function finish() {
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

        {step === 0 && <KeysStep onNext={next} />}
        {step === 1 && <AvatarVoiceStep onNext={next} onBack={back} />}
        {step === 2 && <ConsentStep onNext={next} onBack={back} />}
        {step === 3 && <TikTokStep onNext={next} onBack={back} />}
        {step === 4 && <SeedsStep onNext={next} onBack={back} />}
        {step === 5 && <ReviewStep steps={status.data?.steps} onBack={back} onFinish={finish} />}
      </main>
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

// --- Step 1: API keys ---
const REQUIRED_KEYS = [
  { id: "heygen", label: "HeyGen" },
  { id: "elevenlabs", label: "ElevenLabs" },
  { id: "fal", label: "fal.ai" },
  { id: "scraper", label: "Scraper (Apify / Firecrawl)" },
  { id: "postpeer", label: "PostPeer" },
  { id: "llm", label: "LLM (Anthropic / OpenAI)" },
];

function KeysStep({ onNext }: { onNext: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, KeyTestResult | "testing">>({});
  const [scraper, setScraper] = useState<"apify" | "firecrawl">("firecrawl");

  async function saveAndTest(id: string) {
    const key = values[id];
    if (!key) return;
    setResults((r) => ({ ...r, [id]: "testing" }));
    try {
      await setupApi.saveKey(id === "scraper" ? scraper : id, key);
      const res = await setupApi.testKey(id === "scraper" ? scraper : id);
      setResults((r) => ({ ...r, [id]: res }));
    } catch (e) {
      setResults((r) => ({ ...r, [id]: { ok: false, error: (e as Error).message } }));
    }
  }

  const allGreen = REQUIRED_KEYS.every((k) => {
    const r = results[k.id];
    return r && r !== "testing" && r.ok;
  });

  return (
    <div className="card stack">
      <strong>Connect your API keys</strong>
      <p className="small muted">Each key is stored in the encrypted secret store. "Test" does a cheap live auth call. All must be green to advance.</p>
      {REQUIRED_KEYS.map((k) => {
        const r = results[k.id];
        return (
          <div key={k.id} className="stack" style={{ gap: "0.35rem" }}>
            <div className="row" style={{ gap: "0.6rem" }}>
              <span style={{ width: "12rem" }}>{k.label}</span>
              <input type="password" className="grow" placeholder="paste key" value={values[k.id] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [k.id]: e.target.value }))} />
              <button className="small" onClick={() => saveAndTest(k.id)} disabled={!values[k.id] || r === "testing"}>
                {r === "testing" ? "…" : "Test"}
              </button>
              <span className="row" style={{ gap: "0.3rem", width: "5rem" }}>
                <span className={`dot ${r && r !== "testing" ? (r.ok ? "ok" : "bad") : "idle"}`} />
                <span className="small muted">
                  {r === "testing" ? "…" : r ? (r.ok ? `${r.latency_ms ?? "?"}ms` : r.error || "fail") : "—"}
                </span>
              </span>
            </div>
            {k.id === "scraper" && (
              <div className="row small" style={{ paddingLeft: "12rem", gap: "1rem" }}>
                <label className="row" style={{ gap: "0.3rem", margin: 0 }}>
                  <input type="radio" style={{ width: "auto" }} checked={scraper === "apify"} onChange={() => setScraper("apify")} /> Apify
                </label>
                <label className="row" style={{ gap: "0.3rem", margin: 0 }}>
                  <input type="radio" style={{ width: "auto" }} checked={scraper === "firecrawl"} onChange={() => setScraper("firecrawl")} /> Firecrawl
                </label>
              </div>
            )}
          </div>
        );
      })}
      <NavButtons onNext={onNext} nextDisabled={!allGreen} />
    </div>
  );
}

// --- Step 2: Avatar + Voice ---
function AvatarVoiceStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [avatarRef, setAvatarRef] = useState("");
  const [voiceRef, setVoiceRef] = useState("");
  const [avatarId, setAvatarId] = useState<string | null>(null);
  const [voiceId, setVoiceId] = useState<string | null>(null);
  const [clip, setClip] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function createAvatar() {
    if (!avatarRef) return;
    setBusy(true);
    try {
      const res = await setupApi.createAvatar(avatarRef);
      setAvatarId(res.avatar_id);
    } catch { /* degrade */ } finally { setBusy(false); }
  }
  async function createVoice() {
    if (!voiceRef) return;
    setBusy(true);
    try {
      const res = await setupApi.createVoice(voiceRef);
      setVoiceId(res.voice_id);
    } catch { /* degrade */ } finally { setBusy(false); }
  }
  async function preview() {
    try {
      const res = await setupApi.avatarPreview();
      setClip(res.clip_url);
    } catch { /* degrade */ }
  }

  return (
    <div className="card stack">
      <strong>Create your reusable avatar + voice</strong>
      <div className="stack" style={{ borderLeft: "2px solid var(--border)", paddingLeft: "0.9rem" }}>
        <label>Consent footage reference (uploaded clip key)</label>
        <div className="row">
          <input className="grow" placeholder="footage_ref (e.g. minio key)" value={avatarRef} onChange={(e) => setAvatarRef(e.target.value)} />
          <button onClick={createAvatar} disabled={!avatarRef || busy}>Create HeyGen avatar</button>
        </div>
        {avatarId && <div className="small check-ok">avatar_id: <span className="mono">{avatarId}</span></div>}
      </div>
      <div className="stack" style={{ borderLeft: "2px solid var(--border)", paddingLeft: "0.9rem" }}>
        <label>Voice sample reference (uploaded audio key)</label>
        <div className="row">
          <input className="grow" placeholder="sample_ref" value={voiceRef} onChange={(e) => setVoiceRef(e.target.value)} />
          <button onClick={createVoice} disabled={!voiceRef || busy}>Create ElevenLabs voice</button>
        </div>
        {voiceId && <div className="small check-ok">voice_id: <span className="mono">{voiceId}</span></div>}
      </div>
      <div className="row">
        <button className="ghost" onClick={preview} disabled={!avatarId}>Render 5s test clip</button>
        {clip && <video src={clip} controls style={{ height: "8rem" }} />}
      </div>
      <NavButtons onNext={onNext} onBack={onBack} nextDisabled={!avatarId || !voiceId} />
    </div>
  );
}

// --- Step 3: Consent ---
const CONSENT_TEXT =
  "I authorize AutoUGC-TH to use my likeness and voice to generate synthetic UGC videos " +
  "for the products I submit. I confirm I am the operator, that this consent is revocable, " +
  "and that all generated content will carry the required AI-generated disclosure.";

function ConsentStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [name, setName] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [hash, setHash] = useState<string | null>(null);

  async function sign() {
    if (!name || !agreed) return;
    try {
      const res = await setupApi.saveConsent(name, new Date().toISOString());
      setHash(res.hash);
    } catch { /* degrade */ }
  }

  return (
    <div className="card stack">
      <strong>Consent record</strong>
      <div className="card" style={{ background: "var(--surface-2)" }}>
        <p style={{ margin: 0 }}>{CONSENT_TEXT}</p>
      </div>
      <label className="row" style={{ gap: "0.5rem", cursor: "pointer" }}>
        <input type="checkbox" style={{ width: "auto" }} checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
        <span>I have read and agree to the above.</span>
      </label>
      <div>
        <label>Typed-name signature</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your full legal name" />
      </div>
      <div className="row">
        <button onClick={sign} disabled={!name || !agreed || !!hash}>Sign consent</button>
        {hash && <span className="small check-ok">Signed · hash <span className="mono">{hash.slice(0, 12)}…</span></span>}
      </div>
      <NavButtons onNext={onNext} onBack={onBack} nextDisabled={!hash} />
    </div>
  );
}

// --- Step 4: TikTok connect ---
function TikTokStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [handle, setHandle] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [expires, setExpires] = useState<string | null>(null);

  async function connect() {
    try {
      const { url } = await setupApi.tiktokOauthUrl();
      const popup = window.open(url, "tiktok-oauth", "width=520,height=680");
      // In a real deployment the callback posts a message with the code; here we listen for it.
      const listener = async (ev: MessageEvent) => {
        if (ev.data?.type === "tiktok_code" && ev.data.code) {
          window.removeEventListener("message", listener);
          popup?.close();
          const res = await setupApi.tiktokCallback(ev.data.code);
          setHandle(res.handle);
          setExpires(res.expires_at ?? null);
          setWarning(res.audit_warning ?? null);
        }
      };
      window.addEventListener("message", listener);
    } catch { /* degrade — backend down */ }
  }

  return (
    <div className="card stack">
      <strong>Connect TikTok</strong>
      <div className="caveat-banner">
        ⚠ New or unaudited accounts may not be able to post immediately. Posting will queue and retry.
      </div>
      {handle ? (
        <div className="small check-ok">
          Connected: <strong>@{handle}</strong>
          {expires && <span className="muted"> · token expires {expires}</span>}
        </div>
      ) : (
        <button className="primary" onClick={connect} style={{ alignSelf: "flex-start" }}>Connect TikTok</button>
      )}
      {warning && <div className="small" style={{ color: "var(--amber)" }}>{warning}</div>}
      <NavButtons onNext={onNext} onBack={onBack} nextDisabled={!handle} />
    </div>
  );
}

// --- Step 5: Seeds ---
function SeedsStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [name, setName] = useState("TH-Beauty-Top");
  const [niche, setNiche] = useState("Beauty");
  const [handles, setHandles] = useState("");
  const [hashtags, setHashtags] = useState("");
  const [saved, setSaved] = useState(false);

  async function save() {
    const seed: SeedSet = {
      name,
      niche,
      handles: handles.split(/[\s,]+/).filter(Boolean),
      hashtags: hashtags.split(/[\s,]+/).filter(Boolean),
    };
    try {
      await setupApi.saveSeeds([seed]);
      setSaved(true);
    } catch { setSaved(true); /* allow advancing even if backend down */ }
  }

  return (
    <div className="card stack">
      <strong>Seed accounts for swipe mining</strong>
      <p className="small muted">Define the mining set that feeds the Swipe Library (§2). Editable later in Settings.</p>
      <div className="row wrap">
        <div className="grow"><label>Seed set name</label><input value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div className="grow"><label>Niche</label><input value={niche} onChange={(e) => setNiche(e.target.value)} /></div>
      </div>
      <div><label>TikTok handles (space/comma separated)</label><input value={handles} onChange={(e) => setHandles(e.target.value)} placeholder="@creator1 @creator2" /></div>
      <div><label>Hashtags / sound IDs</label><input value={hashtags} onChange={(e) => setHashtags(e.target.value)} placeholder="#skincare #รีวิว" /></div>
      <div className="row">
        <button onClick={save}>Save seed set</button>
        {saved && <span className="small check-ok">Saved</span>}
      </div>
      <NavButtons onNext={onNext} onBack={onBack} />
    </div>
  );
}

// --- Step 6: Review ---
function ReviewStep({ steps, onBack, onFinish }: { steps?: Record<string, boolean>; onBack: () => void; onFinish: () => void }) {
  const rows = [
    ["API keys", steps?.keys],
    ["Avatar", steps?.avatar],
    ["Voice", steps?.voice],
    ["Consent", steps?.consent],
    ["TikTok", steps?.tiktok],
    ["Seeds", steps?.seeds],
  ] as const;
  return (
    <div className="card stack">
      <strong>Review + finish</strong>
      {rows.map(([label, ok]) => (
        <div key={label} className="row spread" style={{ borderBottom: "1px solid var(--border)", paddingBottom: "0.4rem" }}>
          <span>{label}</span>
          <span className={ok ? "check-ok" : "muted"}>{ok ? "✓ done" : "— not reported"}</span>
        </div>
      ))}
      <p className="small muted">Finishing flips setup to complete and takes you to the dashboard.</p>
      <div className="row spread">
        <button className="ghost" onClick={onBack}>Back</button>
        <button className="success" onClick={onFinish}>Finish</button>
      </div>
    </div>
  );
}
