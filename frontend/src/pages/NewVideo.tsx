import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useCreateJob, useJob } from "@/api/queries";
import { useJobStream } from "@/hooks/useJobStream";
import { StateBadge } from "@/components/StateBadge";
import { ApiError } from "@/api/client";
import { money } from "@/lib/format";
import { PIPELINE_STAGES } from "@/api/types";
import type { JobState } from "@/api/types";

// Screen 3 (§7A.3): the "one URL in". Renders the URL form, or — once a job exists in the
// route — the WS-driven live progress stepper. AWAITING_APPROVAL routes to the Approval screen.
export function NewVideo() {
  const { id } = useParams();
  if (id) return <LiveProgress jobId={id} />;
  return <UrlForm />;
}

function UrlForm() {
  const nav = useNavigate();
  const create = useCreateJob();
  const [url, setUrl] = useState("");
  const [showOpts, setShowOpts] = useState(false);
  const [seedSet, setSeedSet] = useState("");
  const [duration, setDuration] = useState(30);
  const [error, setError] = useState<string | null>(null);

  const validUrl = /^https?:\/\/.+\..+/.test(url.trim());

  async function start() {
    setError(null);
    try {
      const res = await create.mutateAsync({
        product_url: url.trim(),
        seed_set: seedSet || undefined,
        duration_s: duration,
      });
      nav(`/jobs/${res.job_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to start job");
    }
  }

  return (
    <div style={{ maxWidth: "34rem" }}>
      <h1 className="page-title">New Video</h1>
      <div className="card stack">
        <div>
          <label>Product URL</label>
          <input
            autoFocus
            placeholder="https://shop.example/collagen-serum"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && validUrl && start()}
          />
          {url && !validUrl && <div className="small" style={{ color: "var(--red)" }}>Enter a valid product URL.</div>}
        </div>

        <button className="ghost small" onClick={() => setShowOpts((v) => !v)} style={{ alignSelf: "flex-start" }}>
          {showOpts ? "⌃" : "⌄"} Options (niche · seed set · duration)
        </button>
        {showOpts && (
          <div className="stack" style={{ borderLeft: "2px solid var(--border)", paddingLeft: "0.9rem" }}>
            <div>
              <label>Seed set</label>
              <input placeholder="TH-Beauty-Top (default)" value={seedSet} onChange={(e) => setSeedSet(e.target.value)} />
            </div>
            <div>
              <label>Target duration (s)</label>
              <input type="number" min={10} max={90} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
            </div>
          </div>
        )}

        {error && <div className="small" style={{ color: "var(--red)" }}>{error}</div>}

        <div className="row spread">
          <span className="small muted">One URL in → walk away → one approval out.</span>
          <button className="primary" disabled={!validUrl || create.isPending} onClick={start}>
            {create.isPending ? "Starting…" : "Start"}
          </button>
        </div>
      </div>
    </div>
  );
}

// Stages shown in the stepper (drop terminal-only states; POSTING/POSTED shown when reached).
const STEPPER: JobState[] = PIPELINE_STAGES.filter((s) => s !== "QUEUED");

function stageStatus(current: JobState, stage: JobState): "done" | "active" | "pending" | "error" {
  const order = PIPELINE_STAGES;
  if (current === "FAILED") {
    // Mark everything up to last known progress as done; the failing stage is error.
    return "pending";
  }
  const ci = order.indexOf(current);
  const si = order.indexOf(stage);
  if (ci < 0 || si < 0) return "pending";
  if (si < ci) return "done";
  if (si === ci) return "active";
  return "pending";
}

const ARTIFACT_LABEL: Record<string, string> = {
  product_facts: "product facts",
  hook: "hook",
  script: "script draft",
  first_frame: "first avatar frame",
};

function LiveProgress({ jobId }: { jobId: string }) {
  const nav = useNavigate();
  const jobQuery = useJob(jobId);
  const stream = useJobStream(jobId);
  const job = jobQuery.data;

  // Auto-route to approval when the gate is reached (§7A.3).
  if (job?.state === "AWAITING_APPROVAL") {
    return (
      <div style={{ maxWidth: "34rem" }}>
        <h1 className="page-title">{job.product || "Video"}</h1>
        <div className="card stack">
          <div className="row"><StateBadge state="AWAITING_APPROVAL" /><span>Ready for your review.</span></div>
          <button className="primary" onClick={() => nav(`/approve/${jobId}`)}>Go to approval →</button>
        </div>
      </div>
    );
  }

  const isBackendDown =
    jobQuery.isError && jobQuery.error instanceof ApiError && jobQuery.error.status === 0;

  if (isBackendDown) {
    return (
      <div style={{ maxWidth: "34rem" }}>
        <h1 className="page-title">Building…</h1>
        <div className="card">
          <div className="muted">
            Live progress streams over WebSocket. Waiting for the backend — socket status:{" "}
            <strong>{stream.status}</strong>.
          </div>
        </div>
      </div>
    );
  }

  const current = job?.state ?? "QUEUED";
  const pct = stream.progressPct ?? job?.progress ?? 0;

  return (
    <div style={{ maxWidth: "36rem" }}>
      <div className="row spread" style={{ marginBottom: "1rem" }}>
        <h1 className="page-title" style={{ margin: 0 }}>
          {job?.product || "Building…"}
        </h1>
        <span className="chip mono">{money(job?.cost)}</span>
      </div>

      {stream.status !== "open" && (
        <div className="small muted" style={{ marginBottom: "0.75rem" }}>
          socket: {stream.status} · falling back to polling
        </div>
      )}

      {current === "FAILED" && (
        <div className="caveat-banner" style={{ background: "var(--red-bg)", borderColor: "#5c2130", color: "var(--red)" }}>
          ✗ Failed{stream.lastError ? ` at ${stream.lastError.stage}: ${stream.lastError.message}` : ""}.
          {stream.lastError?.retryable && " Retryable — retry from the dashboard."}
        </div>
      )}

      <div className="card stack">
        {STEPPER.map((stage) => {
          const st = current === "FAILED" ? "pending" : stageStatus(current, stage);
          const icon = st === "done" ? "✓" : st === "active" ? "◐" : "○";
          const artifactKind = STAGE_ARTIFACT[stage];
          const artifactRef = artifactKind ? stream.artifacts[artifactKind] : undefined;
          return (
            <div key={stage} className="row" style={{ alignItems: "flex-start" }}>
              <span style={{ width: "1.5rem", color: st === "done" ? "var(--green)" : st === "active" ? "var(--accent)" : "var(--text-dim)" }}>
                {icon}
              </span>
              <div className="grow">
                <div className="row spread">
                  <strong style={{ color: st === "pending" ? "var(--text-dim)" : "var(--text)" }}>
                    {STAGE_LABEL[stage]}
                  </strong>
                  {st === "active" && <span className="small muted">{pct}%</span>}
                </div>
                {artifactRef && (
                  <div className="small muted">
                    {ARTIFACT_LABEL[artifactKind!]} ✓{" "}
                    <span className="mono">{truncate(artifactRef)}</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const STAGE_LABEL: Record<JobState, string> = {
  QUEUED: "Queued",
  RESEARCHING: "Research + swipe mining",
  SCRIPTING: "Scripting (claim-safe Thai)",
  GENERATING: "Generating (avatar + b-roll + TTS)",
  EDITING: "Editing / re-cut",
  CAPTIONING: "Captioning (Thai burn-in)",
  AWAITING_APPROVAL: "Awaiting approval",
  POSTING: "Posting",
  POSTED: "Posted",
  FAILED: "Failed",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};

// Which artifact kind lands during which stage (for inline "it's working" previews).
const STAGE_ARTIFACT: Partial<Record<JobState, string>> = {
  RESEARCHING: "product_facts",
  SCRIPTING: "script",
  GENERATING: "first_frame",
};

function truncate(s: string, n = 48): string {
  return s.length > n ? s.slice(0, n) + "…" : s;
}
