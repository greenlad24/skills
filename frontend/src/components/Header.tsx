import { useNavigate } from "react-router-dom";
import { useUiStore } from "@/store/uiStore";
import { useBudget } from "@/api/queries";

// Persistent header (§7A.2): cost-to-date chip + budget-guard state + New Video button.
// Cost is pushed live by WS "cost" events into the Zustand store; the monthly budget cap
// comes from settings (falls back gracefully if the backend is down).
export function Header() {
  const nav = useNavigate();
  const { costDay, guard } = useUiStore();
  const budget = useBudget();
  const monthlyCap = budget.data?.monthly_cap_usd;

  return (
    <header className="app-header">
      <span className="brand">AutoUGC-TH</span>
      <div className="grow" />
      <span className="chip" title="Cost to date today / monthly budget cap">
        💰 ${costDay.toFixed(2)}
        {monthlyCap != null ? ` / $${monthlyCap.toFixed(0)} mo` : ""}
      </span>
      <span className="chip">
        guard: <strong className={`guard-${guard}`}>{guard}</strong>
      </span>
      <button className="primary" onClick={() => nav("/new")}>
        + New Video
      </button>
    </header>
  );
}
