// Local UI state only (§7A.9). Nothing durable — server truth lives in TanStack Query.
import { create } from "zustand";
import type { GuardState } from "@/api/types";

interface UiState {
  // Live cost header chip, pushed by WS "cost" events.
  costDay: number;
  costMonth: number;
  guard: GuardState;
  setCost: (partial: Partial<Pick<UiState, "costDay" | "costMonth" | "guard">>) => void;

  // Wizard progress (client-side step cursor; completion persists server-side).
  wizardStep: number;
  setWizardStep: (n: number) => void;

  // Caption draft before it's saved via PATCH.
  captionDraft: Record<string, { caption: string; hashtags: string[] }>;
  setCaptionDraft: (jobId: string, v: { caption: string; hashtags: string[] }) => void;

  // Generic modal/toast channel.
  toast: { kind: "info" | "error" | "success"; message: string } | null;
  setToast: (t: UiState["toast"]) => void;
}

export const useUiStore = create<UiState>((set) => ({
  costDay: 0,
  costMonth: 0,
  guard: "OK",
  setCost: (partial) => set((s) => ({ ...s, ...partial })),

  wizardStep: 0,
  setWizardStep: (n) => set({ wizardStep: n }),

  captionDraft: {},
  setCaptionDraft: (jobId, v) =>
    set((s) => ({ captionDraft: { ...s.captionDraft, [jobId]: v } })),

  toast: null,
  setToast: (t) => set({ toast: t }),
}));
