import type { JobState } from "@/api/types";

// Maps each state-machine value to a badge class (§7A.2 "badges map 1:1 to the state machine").
const CLASS: Record<JobState, string> = {
  QUEUED: "queued",
  RESEARCHING: "progress",
  SCRIPTING: "progress",
  GENERATING: "progress",
  EDITING: "progress",
  CAPTIONING: "progress",
  AWAITING_APPROVAL: "approval",
  POSTING: "posting",
  POSTED: "posted",
  FAILED: "failed",
  REJECTED: "rejected",
  CANCELLED: "rejected",
};

const ICON: Partial<Record<JobState, string>> = {
  AWAITING_APPROVAL: "⏳",
  POSTED: "✓",
  FAILED: "✗",
  REJECTED: "⊘",
  CANCELLED: "⊘",
};

export function StateBadge({ state }: { state: JobState }) {
  return (
    <span className={`badge ${CLASS[state]}`}>
      {ICON[state] ? `${ICON[state]} ` : ""}
      {state}
    </span>
  );
}
