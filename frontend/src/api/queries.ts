// TanStack Query hooks — the single server-cache source of truth (§7A.9).
// The WS stream pushes deltas into this same cache via queryClient.setQueryData
// (see hooks/useJobStream.ts), so tables and progress views update live without polling.

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  analyticsApi,
  jobsApi,
  libraryApi,
  settingsApi,
  setupApi,
} from "./client";
import type {
  ApprovedClaim,
  BudgetSettings,
  CaptionUpdate,
  ComplianceSettings,
  JobCreateBody,
  JobState,
  RerollBody,
  SeedSet,
  TemplateType,
} from "./types";

export const qk = {
  setupStatus: ["setup", "status"] as const,
  jobs: (state?: JobState) => ["jobs", { state: state ?? "all" }] as const,
  job: (id: string) => ["job", id] as const,
  library: (seed?: string, type?: TemplateType) =>
    ["library", { seed: seed ?? "all", type: type ?? "all" }] as const,
  analyticsVideos: ["analytics", "videos"] as const,
  leaderboard: ["analytics", "leaderboard"] as const,
  providers: ["settings", "providers"] as const,
  budget: ["settings", "budget"] as const,
  compliance: ["settings", "compliance"] as const,
  claims: ["settings", "claims"] as const,
};

// --- Setup ---
export function useSetupStatus() {
  return useQuery({
    queryKey: qk.setupStatus,
    queryFn: setupApi.status,
    // Poll while wizard is open; cheap and keeps resumable steps fresh.
    refetchInterval: (q) => (q.state.data?.complete ? false : 5000),
    retry: false,
  });
}

// --- Jobs ---
export function useJobs(state?: JobState) {
  return useQuery({
    queryKey: qk.jobs(state),
    queryFn: () => jobsApi.list(state ? { state } : undefined),
    // Polling fallback if the socket drops (§7A.9); WS keeps it fresher than this.
    refetchInterval: 15000,
    retry: false,
  });
}

export function useJob(id: string | undefined) {
  return useQuery({
    queryKey: qk.job(id ?? "none"),
    queryFn: () => jobsApi.get(id as string),
    enabled: !!id,
    retry: false,
  });
}

export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JobCreateBody) => jobsApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useSaveCaption(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CaptionUpdate) => jobsApi.saveCaption(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.job(id) }),
  });
}

export function useApprove(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => jobsApi.approve(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.job(id) });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useReroll(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RerollBody) => jobsApi.reroll(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.job(id) });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useReject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => jobsApi.reject(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.job(id) });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useMarkTagged(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => jobsApi.tagged(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.job(id) }),
  });
}

export function useRetry(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => jobsApi.retry(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

// --- Library ---
export function useLibrary(seed?: string, type?: TemplateType) {
  return useQuery({
    queryKey: qk.library(seed, type),
    queryFn: () => libraryApi.list({ seed_set: seed, type }),
    retry: false,
  });
}

export function useRefreshMining() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (seed?: string) => libraryApi.refresh(seed),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["library"] }),
  });
}

// --- Analytics ---
export function useAnalyticsVideos() {
  return useQuery({
    queryKey: qk.analyticsVideos,
    queryFn: analyticsApi.videos,
    retry: false,
  });
}
export function useLeaderboard() {
  return useQuery({
    queryKey: qk.leaderboard,
    queryFn: analyticsApi.leaderboard,
    retry: false,
  });
}

// --- Settings ---
export function useProviders() {
  return useQuery({ queryKey: qk.providers, queryFn: settingsApi.getProviders, retry: false });
}
export function useBudget() {
  return useQuery({ queryKey: qk.budget, queryFn: settingsApi.getBudget, retry: false });
}
export function useCompliance() {
  return useQuery({ queryKey: qk.compliance, queryFn: settingsApi.getCompliance, retry: false });
}
export function useClaims() {
  return useQuery({ queryKey: qk.claims, queryFn: settingsApi.getClaims, retry: false });
}

export function useSaveBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: BudgetSettings) => settingsApi.putBudget(b),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.budget }),
  });
}
export function useSaveCompliance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (c: ComplianceSettings) => settingsApi.putCompliance(c),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.compliance }),
  });
}
export function useAddClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (c: Omit<ApprovedClaim, "id">) => settingsApi.addClaim(c),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.claims }),
  });
}
export function useDeleteClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => settingsApi.deleteClaim(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.claims }),
  });
}
export function useSaveSeeds() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (seeds: SeedSet[]) => setupApi.saveSeeds(seeds),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.setupStatus }),
  });
}
