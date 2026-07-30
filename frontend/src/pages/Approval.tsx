import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  useApprove,
  useJob,
  useMarkTagged,
  useReject,
  useReroll,
  useSaveCaption,
} from "@/api/queries";
import { useJobStream } from "@/hooks/useJobStream";
import { Modal } from "@/components/Modal";
import { BackendDown } from "@/components/EmptyState";
import { ApiError } from "@/api/client";
import { useUiStore } from "@/store/uiStore";
import type { FlaggedClaim, RerollStage } from "@/api/types";

// Screen 4 (§7A.4): the single human gate. Two columns — verify (left) / decide (right).
// Approve is physically disabled until compliance is all-green (no override in v1).
export function Approval() {
  const { id } = useParams();
  const nav = useNavigate();
  const jobQuery = useJob(id);
  useJobStream(id); // keep the job fresh while it's the gate
  const setToast = useUiStore((s) => s.setToast);

  const approve = useApprove(id!);
  const reject = useReject(id!);
  const reroll = useReroll(id!);
  const saveCaption = useSaveCaption(id!);
  const markTagged = useMarkTagged(id!);

  const [caption, setCaption] = useState("");
  const [hashtags, setHashtags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");
  const [showReroll, setShowReroll] = useState(false);
  const [showTagReminder, setShowTagReminder] = useState(false);

  const job = jobQuery.data;

  // Hydrate the editable caption once the job loads.
  useEffect(() => {
    if (job) {
      setCaption(job.caption ?? "");
      setHashtags(job.hashtags ?? []);
    }
  }, [job?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Surface the post-publish Shop-tag reminder as soon as the job reaches POSTED.
  useEffect(() => {
    if (job?.state === "POSTED" && job.post && !job.post.tagged) {
      setShowTagReminder(true);
    }
  }, [job?.state, job?.post?.tagged]); // eslint-disable-line react-hooks/exhaustive-deps

  if (jobQuery.isError && jobQuery.error instanceof ApiError && jobQuery.error.status === 0) {
    return <BackendDown message="Cannot load the job to approve." />;
  }
  if (jobQuery.isLoading) return <div className="empty">Loading…</div>;
  if (!job) return <div className="empty">Job not found.</div>;

  const allGreen = job.compliance.all_green;
  const captionLen = caption.length;

  async function persistCaption() {
    try {
      await saveCaption.mutateAsync({ caption, hashtags });
    } catch {
      setToast({ kind: "error", message: "Could not save caption" });
    }
  }

  async function doApprove() {
    try {
      await approve.mutateAsync();
      setToast({ kind: "success", message: "Approved → posting" });
    } catch (e) {
      // 409 = compliance not all-green (server-side hard gate).
      if (e instanceof ApiError && e.status === 409) {
        setToast({ kind: "error", message: "Blocked: compliance is not all-green." });
      } else {
        setToast({ kind: "error", message: e instanceof ApiError ? e.message : "Approve failed" });
      }
    }
  }

  async function doReject() {
    if (!confirm("Reject this video? This is terminal.")) return;
    await reject.mutateAsync().catch(() => {});
    nav("/");
  }

  async function doReroll(stage: RerollStage, note: string) {
    try {
      await reroll.mutateAsync({ stage, note: note || undefined });
      setShowReroll(false);
      setToast({ kind: "info", message: `Re-rolling ${stage}…` });
      nav(`/jobs/${job!.id}`);
    } catch (e) {
      setToast({ kind: "error", message: e instanceof ApiError ? e.message : "Re-roll failed" });
    }
  }

  return (
    <div>
      <div className="row spread" style={{ marginBottom: "1rem" }}>
        <h1 className="page-title" style={{ margin: 0 }}>Approve · {job.product || "Video"}</h1>
        <button className="ghost small" onClick={() => nav("/")}>← Dashboard</button>
      </div>

      <div className="approval-grid">
        {/* LEFT — verify */}
        <div className="stack">
          {job.video_url ? (
            <video className="video-portrait" src={job.video_url} controls muted loop playsInline />
          ) : (
            <div className="video-portrait" style={{ display: "grid", placeItems: "center", color: "var(--text-dim)" }}>
              9:16 preview<br />(pending render)
            </div>
          )}
          {job.video_url && (
            <a className="chip" href={job.video_url} download>
              ⬇ Download
            </a>
          )}
        </div>

        {/* RIGHT — decide */}
        <div className="stack">
          {/* 1. Compliance checklist — the hard gate */}
          <div className="card">
            <div className="row spread" style={{ marginBottom: "0.5rem" }}>
              <strong>Compliance</strong>
              <span className={allGreen ? "check-ok" : "check-bad"}>
                {allGreen ? "all green ✓" : "not all green"}
              </span>
            </div>
            {job.compliance.items.length === 0 && (
              <div className="small muted">No compliance items reported yet.</div>
            )}
            {job.compliance.items.map((item) => (
              <div key={item.id} className="checklist-item">
                <span className={item.pass ? "check-ok" : "check-bad"}>{item.pass ? "✓" : "✗"}</span>
                <div>
                  <div>{item.label}</div>
                  {!item.pass && item.reason && <div className="small check-bad">{item.reason}</div>}
                </div>
              </div>
            ))}
          </div>

          {/* 2. Script + flagged claims */}
          <div className="card">
            <strong>Script</strong>
            <p style={{ whiteSpace: "pre-wrap", margin: "0.5rem 0" }} lang="th">
              {job.script || <span className="muted">No script.</span>}
            </p>
            {job.flagged_claims.length > 0 && (
              <div className="stack">
                {job.flagged_claims.map((c: FlaggedClaim, i) => (
                  <div key={i} className="small">
                    ⚑ <span className="flag" lang="th">{c.phrase ?? "flagged phrase"}</span>{" "}
                    {c.reason && <span className="muted">— {c.reason}</span>}
                    {c.safe_variant && (
                      <> → replaced with <span className="check-ok" lang="th">{c.safe_variant}</span></>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 3. Editable caption + hashtags */}
          <div className="card stack">
            <div className="row spread">
              <strong>Caption</strong>
              <span className="small muted">{captionLen}/150</span>
            </div>
            <textarea
              rows={3}
              value={caption}
              maxLength={2200}
              onChange={(e) => setCaption(e.target.value)}
              onBlur={persistCaption}
              lang="th"
            />
            <div className="row wrap" style={{ gap: "0.4rem" }}>
              {hashtags.map((t, i) => (
                <span key={i} className="chip">
                  {t}
                  <button
                    className="ghost"
                    style={{ border: "none", padding: 0, marginLeft: "0.25rem" }}
                    onClick={() => {
                      const next = hashtags.filter((_, j) => j !== i);
                      setHashtags(next);
                      saveCaption.mutate({ caption, hashtags: next });
                    }}
                  >
                    ✕
                  </button>
                </span>
              ))}
              <input
                style={{ width: "8rem" }}
                placeholder="+ hashtag"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newTag.trim()) {
                    const tag = newTag.trim().startsWith("#") ? newTag.trim() : `#${newTag.trim()}`;
                    const next = [...hashtags, tag];
                    setHashtags(next);
                    setNewTag("");
                    saveCaption.mutate({ caption, hashtags: next });
                  }
                }}
              />
            </div>
          </div>

          {/* 4. Actions */}
          <div className="row spread wrap">
            <button className="danger" onClick={doReject} disabled={reject.isPending}>Reject</button>
            <div className="pill-actions">
              <button onClick={() => setShowReroll(true)} disabled={reroll.isPending}>Request re-roll ⌄</button>
              <button
                className="success"
                disabled={!allGreen || approve.isPending}
                title={allGreen ? "" : "Disabled until every compliance item is green"}
                onClick={doApprove}
              >
                ✅ Approve → Post
              </button>
            </div>
          </div>
          {!allGreen && (
            <div className="small check-bad">Approve is disabled until the compliance checklist is all-green.</div>
          )}
        </div>
      </div>

      {showReroll && (
        <RerollModal onClose={() => setShowReroll(false)} onSubmit={doReroll} pending={reroll.isPending} />
      )}
      {showTagReminder && job.post && (
        <TagReminderModal
          deepLink={job.post.deep_link}
          tiktokUrl={job.post.tiktok_url}
          onTagged={async () => {
            await markTagged.mutateAsync().catch(() => {});
            setShowTagReminder(false);
            nav("/");
          }}
          onClose={() => setShowTagReminder(false)}
        />
      )}
    </div>
  );
}

const REROLL_STAGES: { value: RerollStage; label: string; cost: string }[] = [
  { value: "script", label: "Script (re-write claim-safe draft)", cost: "~$0.02 LLM" },
  { value: "voice", label: "Voice (re-synthesize TTS)", cost: "~$0.15 TTS" },
  { value: "broll", label: "B-roll (regenerate visuals)", cost: "~$1.20 gen" },
  { value: "recut", label: "Re-cut (cheap re-assembly, no regen)", cost: "~$0.00" },
];

function RerollModal({
  onClose,
  onSubmit,
  pending,
}: {
  onClose: () => void;
  onSubmit: (stage: RerollStage, note: string) => void;
  pending: boolean;
}) {
  const [stage, setStage] = useState<RerollStage>("recut");
  const [note, setNote] = useState("");
  const cost = REROLL_STAGES.find((s) => s.value === stage)?.cost;
  return (
    <Modal title="Request re-roll" onClose={onClose}>
      <div className="stack">
        <div>
          <label>Which stage?</label>
          <select value={stage} onChange={(e) => setStage(e.target.value as RerollStage)}>
            {REROLL_STAGES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
        <div className="small muted">Cost implication: {cost}</div>
        <div>
          <label>Note (optional)</label>
          <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. hook feels slow, tighten first 2s" />
        </div>
        <div className="row spread">
          <button className="ghost" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={pending} onClick={() => onSubmit(stage, note)}>
            {pending ? "Submitting…" : "Re-roll"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function TagReminderModal({
  deepLink,
  tiktokUrl,
  onTagged,
  onClose,
}: {
  deepLink?: string | null;
  tiktokUrl?: string | null;
  onTagged: () => void;
  onClose: () => void;
}) {
  return (
    <Modal title="Posted ✓ — one manual step" onClose={onClose}>
      <div className="stack">
        <p>
          Now tag the product in <strong>TikTok Shop</strong>. This is the one step that isn't automated.
        </p>
        {(deepLink || tiktokUrl) && (
          <a className="chip" href={deepLink || tiktokUrl || "#"} target="_blank" rel="noreferrer">
            ↗ Open the posted video
          </a>
        )}
        <label className="row" style={{ gap: "0.5rem", cursor: "pointer" }}>
          <input type="checkbox" style={{ width: "auto" }} onChange={(e) => e.target.checked && onTagged()} />
          <span>I've attached the TikTok-Shop product tag</span>
        </label>
      </div>
    </Modal>
  );
}
