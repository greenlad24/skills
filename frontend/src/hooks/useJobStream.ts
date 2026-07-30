// Bridges the multiplexed WebSocket into the TanStack Query cache (§7A.9):
// "every WS event maps to a Query cache update — no separate client state model."
//
// - useGlobalJobStream(): mounted once at the app root; subscribes to all jobs and
//   folds state/progress/cost/posted events into the job caches + the cost header chip.
// - useJobStream(jobId): opt-in per-screen; ensures the socket is subscribed to one job
//   and exposes the latest artifacts / error for the live progress + approval views.

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { jobStream } from "@/api/ws";
import type { WsStatus } from "@/api/ws";
import { qk } from "@/api/queries";
import { useUiStore } from "@/store/uiStore";
import type {
  Job,
  JobListResponse,
  WSArtifactEvent,
  WSEvent,
} from "@/api/types";

function patchJobCaches(qc: ReturnType<typeof useQueryClient>, jobId: string, patch: Partial<Job>) {
  // Full job cache.
  qc.setQueryData<Job>(qk.job(jobId), (old) => (old ? { ...old, ...patch } : old));
  // Every jobs list cache (all/filtered) — update the matching row in place.
  qc.setQueriesData<JobListResponse>({ queryKey: ["jobs"] }, (old) => {
    if (!old) return old;
    return {
      ...old,
      jobs: old.jobs.map((j) =>
        j.id === jobId
          ? {
              ...j,
              ...(patch.state !== undefined ? { state: patch.state } : {}),
              ...(patch.progress !== undefined ? { progress: patch.progress } : {}),
              ...(patch.cost !== undefined ? { cost: patch.cost } : {}),
            }
          : j,
      ),
    };
  });
}

/** App-root subscription: keep the whole dashboard + cost chip live. */
export function useGlobalJobStream() {
  const qc = useQueryClient();
  const setCost = useUiStore((s) => s.setCost);

  useEffect(() => {
    const off = jobStream.addListener((ev: WSEvent) => {
      switch (ev.type) {
        case "state":
          patchJobCaches(qc, ev.job_id, { state: ev.state });
          break;
        case "progress":
          patchJobCaches(qc, ev.job_id, { progress: ev.pct, cost: ev.cost });
          break;
        case "cost":
          patchJobCaches(qc, ev.job_id, { cost: ev.job });
          setCost({ costDay: ev.day, guard: ev.guard });
          break;
        case "awaiting_approval":
          patchJobCaches(qc, ev.job_id, { state: "AWAITING_APPROVAL" });
          qc.invalidateQueries({ queryKey: qk.job(ev.job_id) });
          break;
        case "posted":
          patchJobCaches(qc, ev.job_id, { state: "POSTED" });
          qc.invalidateQueries({ queryKey: qk.job(ev.job_id) });
          break;
        case "error":
          // A retryable error keeps the row; a hard error will land as a state=FAILED event.
          qc.invalidateQueries({ queryKey: qk.job(ev.job_id) });
          break;
      }
    });
    jobStream.subscribeAll();
    return off;
  }, [qc, setCost]);
}

export interface JobStreamView {
  status: WsStatus;
  artifacts: Record<string, string>; // kind -> ref
  lastError: { stage: string; message: string; retryable: boolean } | null;
  progressPct: number | null;
}

/** Per-job subscription for the live progress + approval screens. */
export function useJobStream(jobId: string | undefined): JobStreamView {
  const qc = useQueryClient();
  const [status, setStatus] = useState<WsStatus>(jobStream.getStatus());
  const [artifacts, setArtifacts] = useState<Record<string, string>>({});
  const [lastError, setLastError] = useState<JobStreamView["lastError"]>(null);
  const [progressPct, setProgressPct] = useState<number | null>(null);
  const idRef = useRef(jobId);
  idRef.current = jobId;

  useEffect(() => {
    if (!jobId) return;
    setArtifacts({});
    setLastError(null);
    setProgressPct(null);

    const offStatus = jobStream.onStatus(setStatus);
    const off = jobStream.addListener((ev: WSEvent) => {
      if (ev.job_id !== idRef.current) return;
      switch (ev.type) {
        case "artifact": {
          const a = ev as WSArtifactEvent;
          setArtifacts((prev) => ({ ...prev, [a.kind]: a.ref }));
          break;
        }
        case "progress":
          setProgressPct(ev.pct);
          break;
        case "error":
          setLastError({ stage: ev.stage, message: ev.message, retryable: ev.retryable });
          break;
        case "awaiting_approval":
        case "posted":
        case "state":
          // Refetch full job so the approval screen has script/compliance/video_url.
          qc.invalidateQueries({ queryKey: qk.job(ev.job_id) });
          break;
      }
    });
    jobStream.subscribeJobs([jobId]);
    return () => {
      off();
      offStatus();
    };
  }, [jobId, qc]);

  return { status, artifacts, lastError, progressPct };
}
