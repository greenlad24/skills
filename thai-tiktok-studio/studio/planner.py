"""Tool 1 — product in, ranked viral scripts + Thai shot lists + edit plans out."""

from __future__ import annotations

import json

from . import compliance, exports, projects, prompts, scrape
from .plan_schema import normalize_plan, plan_problems


def _provider(name: str):
    if name == "openai":
        from . import llm_openai
        return llm_openai
    from . import llm_claude
    return llm_claude


def gather_step(job, pid: str, text: str, image_paths: list, notes: str) -> dict:
    d = projects.pdir(pid)
    gathered = scrape.gather(text, image_paths, d, log=job.say)
    gathered["notes"] = notes
    projects.save_json(d / "gathered.json", gathered)
    return gathered


def run_planning(job, pid: str, text: str, image_paths: list, notes: str, settings: dict) -> dict:
    """Background job: scrape → AI research → AI plan → normalize → export."""
    provider = settings.get("provider", "claude")
    d = projects.pdir(pid)
    projects.update_meta(pid, status="researching")
    job.progress = 0.05
    gathered = gather_step(job, pid, text, image_paths, notes)
    job.progress = 0.15

    if provider == "manual":
        n = int(settings.get("videos_per_product", 5))
        (d / "manual_prompt.txt").write_text(prompts.manual_prompt(gathered, n), "utf-8")
        projects.update_meta(pid, status="waiting_for_paste")
        job.say("Prompt ready — copy it into ChatGPT or Claude, then paste the JSON answer back.")
        return {"manual": True}

    mod = _provider(provider)
    key = settings.get("anthropic_api_key" if provider == "claude" else "openai_api_key")
    if not key:
        raise RuntimeError(f"No API key for {provider}. Add it in Settings, or switch to the free copy/paste mode.")
    try:
        dossier = mod.research(gathered, settings, log=job.say)
        (d / "research.md").write_text(dossier or "", "utf-8")
        job.say("Research done.")
        job.progress = 0.45
        projects.update_meta(pid, status="writing")
        raw = mod.make_plan(gathered, dossier, settings, log=job.say)
    except Exception as e:
        msg = mod.explain_error(e) if hasattr(mod, "explain_error") else str(e)
        projects.update_meta(pid, status="error")
        raise RuntimeError(msg) from e
    job.progress = 0.9
    return finalize_plan(pid, raw, job.say)


def finalize_plan(pid: str, raw: dict, log=print) -> dict:
    d = projects.pdir(pid)
    projects.save_json(d / "raw_plan.json", raw)
    plan = normalize_plan(raw)
    projects.save_json(d / "plan.json", plan)
    warnings = plan_problems(plan)
    flags = compliance.check_plan(plan)
    projects.save_json(d / "checks.json", {"warnings": warnings, "compliance": flags})
    exports.write_all(d, plan, projects.meta(pid))
    name = plan["research"].get("product_name") or projects.meta(pid).get("name")
    projects.update_meta(pid, status="planned", name=name)
    log(f"Plan ready: {len(plan['videos'])} videos.")
    for w in warnings:
        log("Note: " + w)
    hard = sum(1 for v in flags.values() for f in v if f["level"] == "hard")
    if hard:
        log(f"Compliance: {hard} risky phrase(s) flagged — review before posting.")
    return {"videos": len(plan["videos"])}


def import_pasted(pid: str, text: str) -> dict:
    """Manual mode: accept the JSON the user pasted from a chat app."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("No JSON object found in the pasted text.")
    try:
        raw = json.loads(t[start:end + 1])
    except ValueError as e:
        raise ValueError(f"The pasted text is not valid JSON ({e}). Ask the chat to 'return only valid JSON'.")
    return finalize_plan(pid, raw)
