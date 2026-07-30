// TS types mirroring app/core/schemas.py + the §7A.10 REST/WS contract.
// Kept decoupled from the DB models on purpose (API surface != rows).

// --- Job state machine (verbatim from app/core/state_machine.py::JobState) ---
export type JobState =
  | "QUEUED"
  | "RESEARCHING"
  | "SCRIPTING"
  | "GENERATING"
  | "EDITING"
  | "CAPTIONING"
  | "AWAITING_APPROVAL"
  | "POSTING"
  | "POSTED"
  | "FAILED"
  | "REJECTED"
  | "CANCELLED";

export const JOB_STATES: JobState[] = [
  "QUEUED",
  "RESEARCHING",
  "SCRIPTING",
  "GENERATING",
  "EDITING",
  "CAPTIONING",
  "AWAITING_APPROVAL",
  "POSTING",
  "POSTED",
  "FAILED",
  "REJECTED",
  "CANCELLED",
];

// Ordered pipeline stages for the live progress stepper (terminal/branch states excluded).
export const PIPELINE_STAGES: JobState[] = [
  "QUEUED",
  "RESEARCHING",
  "SCRIPTING",
  "GENERATING",
  "EDITING",
  "CAPTIONING",
  "AWAITING_APPROVAL",
  "POSTING",
  "POSTED",
];

// --- Jobs ---
export interface ComplianceItem {
  id: string;
  label: string;
  pass: boolean;
  reason?: string | null;
}

export interface ComplianceSummary {
  items: ComplianceItem[];
  all_green: boolean;
}

export interface PostSummary {
  tiktok_url?: string | null;
  deep_link?: string | null;
  tagged: boolean;
}

export interface FlaggedClaim {
  phrase?: string;
  reason?: string;
  safe_variant?: string;
  [k: string]: unknown;
}

export interface JobSummary {
  id: string;
  state: JobState;
  product?: string | null;
  progress: number;
  cost: number;
  created_at?: string | null;
  video_url?: string | null;
  // convenience fields some list rows may carry
  views?: number | null;
  fail_reason?: string | null;
}

export interface Job {
  id: string;
  state: JobState;
  product?: string | null;
  progress: number;
  cost: number;
  created_at?: string | null;
  video_url?: string | null;
  script?: string | null;
  flagged_claims: FlaggedClaim[];
  compliance: ComplianceSummary;
  caption?: string | null;
  hashtags: string[];
  post?: PostSummary | null;
}

export interface JobListResponse {
  jobs: JobSummary[];
  cursor?: string | null;
}

export interface JobCreateResponse {
  job_id: string;
  state: JobState;
}

export interface JobCreateBody {
  product_url: string;
  seed_set?: string;
  avatar_id?: string;
  duration_s?: number;
}

export interface CaptionUpdate {
  caption?: string | null;
  hashtags?: string[] | null;
}

export type RerollStage = "script" | "voice" | "broll" | "recut";

export interface RerollBody {
  stage: RerollStage;
  note?: string;
}

export interface DecisionResponse {
  state: JobState;
  from_stage?: string | null;
}

// --- Setup ---
export type SetupStepKey =
  | "keys"
  | "avatar"
  | "voice"
  | "consent"
  | "tiktok"
  | "seeds";

export interface SetupStatus {
  complete: boolean;
  steps: Record<SetupStepKey, boolean>;
}

export interface KeyTestResult {
  ok: boolean;
  latency_ms?: number;
  error?: string;
}

export interface TikTokCallbackResult {
  handle: string;
  expires_at?: string;
  audit_warning?: string;
}

export interface SeedSet {
  name: string;
  niche?: string;
  handles?: string[];
  hashtags?: string[];
  sound_ids?: string[];
}

// --- Library ---
export type TemplateType = "formula" | "hook" | "pacing";

export interface SwipeVideo {
  id: string;
  source_handle?: string;
  thumbnail_url?: string;
  video_url?: string;
  views?: number;
  likes?: number;
  comments?: number;
  shares?: number;
  proxy_score?: number;
  signal_type?: string; // always "engagement_proxy"
  seed_set?: string;
  niche?: string;
}

export interface Template {
  id: string;
  type: TemplateType;
  label: string;
  summary?: string;
  win_score?: number;
  proxy_score?: number;
  operator_win_score?: number;
  signal_type?: string;
}

export interface LibraryResponse {
  proxy_caveat: boolean;
  videos: SwipeVideo[];
  templates: Template[];
}

// --- Analytics ---
export interface VideoPerformance {
  id: string;
  product?: string;
  views?: number;
  likes?: number;
  comments?: number;
  shares?: number;
  full_video_watch_rate?: number;
  product_clicks?: number;
  orders?: number;
  gmv?: number;
  cost?: number;
  views_per_dollar?: number;
  is_winner?: boolean;
  hook_template_id?: string;
  formula_template_id?: string;
  pacing_template_id?: string;
}

export interface LeaderboardEntry {
  template_id: string;
  label: string;
  type: TemplateType;
  win_rate: number;
  sample_size?: number;
}

export interface LeaderboardResponse {
  hooks: LeaderboardEntry[];
  formulas: LeaderboardEntry[];
  pacing: LeaderboardEntry[];
}

// --- Settings ---
export interface ProvidersSettings {
  scraper: "apify" | "firecrawl";
  keys: Record<string, { set: boolean; last_tested?: string; ok?: boolean }>;
  avatar_id?: string;
  voice_id?: string;
}

export interface BudgetSettings {
  per_video_usd: number;
  daily_cap_usd: number;
  monthly_cap_usd: number;
  on_breach: "pause" | "warn";
}

export interface ComplianceSettings {
  disclosure_text: string;
  disclosure_hashtags: string[];
  restricted_keywords: string[];
  strictness: "low" | "medium" | "high";
  reroll_auto_fixes_claims: boolean;
}

export interface ApprovedClaim {
  id: string;
  claim_th: string;
  claim_en?: string;
  evidence_note?: string;
}

// --- WebSocket events (§7A.10) ---
export type GuardState = "OK" | "WARN" | "STOP";

interface WSBase {
  job_id: string;
  ts: string;
}
export interface WSStateEvent extends WSBase {
  type: "state";
  state: JobState;
  prev?: JobState | null;
}
export interface WSProgressEvent extends WSBase {
  type: "progress";
  stage: string;
  pct: number;
  cost: number;
}
export interface WSArtifactEvent extends WSBase {
  type: "artifact";
  kind: "script" | "first_frame" | "hook" | "product_facts";
  ref: string;
}
export interface WSAwaitingApprovalEvent extends WSBase {
  type: "awaiting_approval";
}
export interface WSCostEvent extends WSBase {
  type: "cost";
  job: number;
  day: number;
  guard: GuardState;
}
export interface WSErrorEvent extends WSBase {
  type: "error";
  stage: string;
  message: string;
  retryable: boolean;
}
export interface WSPostedEvent extends WSBase {
  type: "posted";
  tiktok_url: string;
  deep_link?: string | null;
}

export type WSEvent =
  | WSStateEvent
  | WSProgressEvent
  | WSArtifactEvent
  | WSAwaitingApprovalEvent
  | WSCostEvent
  | WSErrorEvent
  | WSPostedEvent;

export type WSClientMessage =
  | { op: "subscribe"; job_ids: string[] }
  | { op: "subscribe_all" };
