"""Claude via your Claude subscription: headless Claude Code + a `claude setup-token` token.

Runs `claude -p` as a local subprocess with CLAUDE_CODE_OAUTH_TOKEN set, so research and
script writing are billed to your Claude plan (Pro/Max/Team), not an API key.
Docs: https://code.claude.com/docs/en/authentication · https://code.claude.com/docs/en/headless
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
from pathlib import Path

from . import prompts
from .plan_schema import PLAN_SCHEMA

CANDIDATES = ["~/.local/bin/claude", "~/.claude/local/claude", "/usr/local/bin/claude", "/opt/homebrew/bin/claude",
              "~/.npm-global/bin/claude"]
TIMEOUT = 45 * 60


def find_claude(custom: str = "") -> str:
    for c in [custom] if custom else []:
        if c and Path(os.path.expanduser(c)).exists():
            return os.path.expanduser(c)
    exe = shutil.which("claude")
    if exe:
        return exe
    for c in CANDIDATES:
        p = Path(os.path.expanduser(c))
        if p.exists():
            return str(p)
    return ""


@functools.lru_cache(maxsize=4)
def _help(exe: str) -> str:
    try:
        return subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def version(exe: str) -> str:
    try:
        return subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _env(token: str) -> dict:
    env = dict(os.environ)
    # These outrank the subscription token — remove them so your Claude plan is used.
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        env.pop(k, None)
    env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env


def _run(prompt: str, settings: dict, workdir: Path, tools: str, schema: dict | None, max_turns: int, log) -> dict:
    exe = find_claude(settings.get("claude_code_path", ""))
    if not exe:
        raise RuntimeError("Claude Code isn't installed on this Mac. Re-run start.command to install it, "
                           "or install it from https://code.claude.com/docs/en/setup")
    token = (settings.get("claude_code_token") or "").strip()
    if not token:
        raise RuntimeError("No Claude setup-token. In Terminal run:  claude setup-token  — then paste the token in Settings.")
    h = _help(exe)
    cmd = [exe, "-p", "Follow the instructions in the piped input exactly.", "--output-format", "json",
           "--max-turns", str(max_turns)]
    if settings.get("claude_model"):
        cmd += ["--model", settings["claude_model"]]
    if tools:
        if "--tools" in h:
            cmd += ["--tools", tools]
        cmd += ["--allowedTools", tools]
    cmd += ["--disallowedTools", "Edit,Write,Bash,NotebookEdit"]
    for flag in ("--safe-mode", "--no-session-persistence"):
        if flag in h:
            cmd.append(flag)
    if "--permission-prompts" in h:
        cmd += ["--permission-prompts", "none"]
    if schema is not None and "--json-schema" in h:
        cmd += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    else:
        schema = None
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=_env(token), cwd=str(workdir),
                       timeout=TIMEOUT)
    out = (p.stdout or "").strip()
    try:
        data = json.loads(out[out.find("{"):]) if out else {}
    except ValueError:
        data = {}
    if p.returncode != 0 or data.get("is_error"):
        msg = data.get("result") or (p.stderr or out or "").strip()[-600:]
        low = msg.lower()
        if "401" in low or "auth" in low or "token" in low or "login" in low:
            msg = "Your Claude setup-token was rejected (expired or wrong). Run  claude setup-token  again and paste the new token in Settings. " + msg[:200]
        elif "usage limit" in low or "rate limit" in low:
            msg = "Your Claude plan's usage limit is reached — try again later. " + msg[:200]
        raise RuntimeError(f"Claude Code: {msg}")
    data["_structured"] = schema is not None
    return data


def _with_images(text: str, gathered: dict, limit: int = 6) -> str:
    imgs = [str(Path(p).resolve()) for p in (gathered.get("user_images", []) + gathered.get("product_images", []))[:limit]
            if Path(p).exists()]
    if not imgs:
        return text
    return text + "\n\nLook at these product images first with the Read tool:\n" + "\n".join(f"- {p}" for p in imgs)


def research(gathered: dict, settings: dict, log=print, workdir: Path | None = None) -> str:
    log("Researching on the web with your Claude account (Claude Code)…")
    data = _run(_with_images(prompts.research_prompt(gathered), gathered), settings, workdir or Path.cwd(),
                "WebSearch,WebFetch,Read", None, 40, log)
    return data.get("result", "")


def make_plan(gathered: dict, dossier: str, settings: dict, log=print, workdir: Path | None = None) -> dict:
    n = int(settings.get("videos_per_product", 5))
    log(f"Writing {n} scripts, shot lists and edit plans with your Claude account…")
    text = prompts.system_prompt(n) + "\n\n---\n\n" + _with_images(prompts.plan_prompt(gathered, dossier, n),
                                                                   {"user_images": gathered.get("user_images", [])})
    text += ("\n\nReply with ONE JSON object only (no markdown fences) matching this JSON Schema; every property "
             "is required:\n" + json.dumps(PLAN_SCHEMA, ensure_ascii=False))
    data = _run(text, settings, workdir or Path.cwd(), "Read", PLAN_SCHEMA, 8, log)
    if isinstance(data.get("structured_output"), dict):
        return data["structured_output"]
    out = data.get("result", "")
    return json.loads(out[out.find("{"): out.rfind("}") + 1])


def explain_error(e: Exception) -> str:
    if isinstance(e, subprocess.TimeoutExpired):
        return "Claude Code took too long (over 45 minutes). Try again, or fewer videos per product."
    return str(e)
