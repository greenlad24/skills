import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useJobs, useRetry } from "@/api/queries";
import { StateBadge } from "@/components/StateBadge";
import { ProgressBar } from "@/components/ProgressBar";
import { EmptyState, BackendDown } from "@/components/EmptyState";
import { ApiError } from "@/api/client";
import { compactNum, isInProgress, money, shortDate } from "@/lib/format";
import type { JobState, JobSummary } from "@/api/types";

type Segment = "all" | "approval" | "progress" | "posted" | "failed";

const SEGMENTS: { key: Segment; label: string }[] = [
  { key: "all", label: "All" },
  { key: "approval", label: "Needs approval" },
  { key: "progress", label: "In progress" },
  { key: "posted", label: "Posted" },
  { key: "failed", label: "Failed" },
];

function matchesSegment(job: JobSummary, seg: Segment): boolean {
  switch (seg) {
    case "all":
      return true;
    case "approval":
      return job.state === "AWAITING_APPROVAL";
    case "progress":
      return isInProgress(job.state);
    case "posted":
      return job.state === "POSTED";
    case "failed":
      return job.state === "FAILED";
  }
}

export function Dashboard() {
  const nav = useNavigate();
  const [seg, setSeg] = useState<Segment>("all");
  const jobsQuery = useJobs();

  const jobs = jobsQuery.data?.jobs ?? [];

  // AWAITING_APPROVAL rows pinned to the top (§7A.2).
  const sorted = useMemo(() => {
    const filtered = jobs.filter((j) => matchesSegment(j, seg));
    return [...filtered].sort((a, b) => {
      const aw = a.state === "AWAITING_APPROVAL" ? 0 : 1;
      const bw = b.state === "AWAITING_APPROVAL" ? 0 : 1;
      if (aw !== bw) return aw - bw;
      return (b.created_at ?? "").localeCompare(a.created_at ?? "");
    });
  }, [jobs, seg]);

  const approvalCount = jobs.filter((j) => j.state === "AWAITING_APPROVAL").length;

  function openJob(job: JobSummary) {
    if (job.state === "AWAITING_APPROVAL") nav(`/approve/${job.id}`);
    else nav(`/jobs/${job.id}`);
  }

  const isBackendDown =
    jobsQuery.isError && jobsQuery.error instanceof ApiError && jobsQuery.error.status === 0;

  return (
    <div>
      <div className="row spread" style={{ marginBottom: "1rem" }}>
        <h1 className="page-title" style={{ margin: 0 }}>Dashboard</h1>
      </div>

      <div className="tabs">
        {SEGMENTS.map((s) => (
          <button
            key={s.key}
            className={`tab ${seg === s.key ? "active" : ""}`}
            onClick={() => setSeg(s.key)}
          >
            {s.label}
            {s.key === "approval" && approvalCount > 0 ? ` • ${approvalCount}` : ""}
          </button>
        ))}
      </div>

      {isBackendDown ? (
        <BackendDown message={(jobsQuery.error as ApiError).message} />
      ) : jobsQuery.isLoading ? (
        <div className="empty">Loading jobs…</div>
      ) : sorted.length === 0 ? (
        <EmptyState
          title="No videos yet"
          hint="Paste a product URL to generate your first UGC video."
          action={<button className="primary" onClick={() => nav("/new")}>+ New Video</button>}
        />
      ) : (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="jobs">
            <thead>
              <tr>
                <th>Product</th>
                <th>State</th>
                <th style={{ width: "22%" }}>Progress</th>
                <th>Cost</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((job) => (
                <tr
                  key={job.id}
                  className={job.state === "AWAITING_APPROVAL" ? "needs-approval" : ""}
                  onClick={() => openJob(job)}
                  style={{ cursor: "pointer" }}
                >
                  <td>
                    {job.state === "AWAITING_APPROVAL" ? "★ " : ""}
                    {job.product || <span className="muted">Untitled job</span>}
                    {job.state === "POSTED" && job.views != null && (
                      <span className="muted small"> · {compactNum(job.views)} views</span>
                    )}
                    {job.state === "FAILED" && job.fail_reason && (
                      <span className="muted small"> · {job.fail_reason}</span>
                    )}
                  </td>
                  <td><StateBadge state={job.state} /></td>
                  <td>
                    <div className="row" style={{ gap: "0.5rem" }}>
                      <div className="grow"><ProgressBar pct={job.progress} /></div>
                      <span className="small muted">{job.progress}%</span>
                    </div>
                  </td>
                  <td className="mono">{money(job.cost)}</td>
                  <td className="small muted">{shortDate(job.created_at)}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <RowAction state={job.state} onOpen={() => openJob(job)} jobId={job.id} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RowAction({
  state,
  onOpen,
  jobId,
}: {
  state: JobState;
  onOpen: () => void;
  jobId: string;
}) {
  const retry = useRetry(jobId);
  if (state === "FAILED") {
    return (
      <button className="small ghost" onClick={() => retry.mutateAsync().catch(() => {})} disabled={retry.isPending}>
        ↻ Retry
      </button>
    );
  }
  if (state === "AWAITING_APPROVAL") {
    return <button className="small primary" onClick={onOpen}>Review →</button>;
  }
  return <button className="small ghost" onClick={onOpen}>Open →</button>;
}
