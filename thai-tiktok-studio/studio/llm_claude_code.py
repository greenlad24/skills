"""Claude via your Claude subscription: headless Claude Code + a `claude setup-token` token.

Runs `claude -p` as a local subprocess with CLAUDE_CODE_OAUTH_TOKEN set, so research and
script writing are billed to your Claude plan (Pro/Max/Team), not an API key.
Docs: https://code.claude.com/docs/en/authentication · https://code.claude.com/docs/en/headless
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import threading
import time
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


# Some Claude Code builds ignore the token when isolation flags are passed ("Not logged in").
# We try the isolated run first and fall back to plain flags, remembering what worked.
_ISOLATION_OK: bool | None = None


def clean_token(token: str) -> str:
    """Remove spaces / line breaks that sneak in when copying a wrapped token from Terminal."""
    return re.sub(r"\s+", "", token or "")


def _not_logged_in(msg: str) -> bool:
    low = msg.lower()
    return "not logged in" in low or "/login" in low or "please run /login" in low


def _attempt(exe, prompt, settings, workdir, tools, schema, max_turns, isolated: bool, token: str,
             log=lambda m: None):
    h = _help(exe)
    cmd = [exe, "-p", "Follow the instructions in the piped input exactly.", "--output-format", "json",
           "--max-turns", str(max_turns)]
    if settings.get("claude_model"):
        cmd += ["--model", settings["claude_model"]]
    if tools:
        if isolated and "--tools" in h:
            cmd += ["--tools", tools]
        cmd += ["--allowedTools", tools]
    cmd += ["--disallowedTools", "Edit,Write,Bash,NotebookEdit"]
    if isolated:
        for flag in ("--safe-mode", "--no-session-persistence"):
            if flag in h:
                cmd.append(flag)
        if "--permission-prompts" in h:
            cmd += ["--permission-prompts", "none"]
    if schema is not None and "--json-schema" in h:
        cmd += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    streaming = "stream-json" in h
    if streaming:   # live progress: every web search / page read shows up in the log
        cmd[cmd.index("--output-format") + 1] = "stream-json"
        cmd.append("--verbose")
    data, raw_lines, err_lines = {}, [], []
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=_env(token), cwd=str(workdir))
    started = time.time()
    done = threading.Event()

    def heartbeat():
        while not done.wait(30):
            log(f"…still working ({int(time.time() - started)} s) — research usually takes 2–6 minutes")
            if time.time() - started > TIMEOUT:
                proc.kill()
                return
    threading.Thread(target=heartbeat, daemon=True).start()
    threading.Thread(target=lambda: err_lines.extend(proc.stderr), daemon=True).start()
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        raw_lines.append(line)
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "result" or "result" in ev and "type" not in ev:
            data = ev
        elif ev.get("type") == "assistant":
            _log_tool_uses(ev, log)
    proc.wait()
    done.set()
    if not data and raw_lines:   # non-streaming JSON (older builds) or a single JSON blob
        blob = "\n".join(raw_lines)
        try:
            data = json.loads(blob[blob.find("{"):])
        except ValueError:
            data = {}
    ok = proc.returncode == 0 and bool(data) and not data.get("is_error")
    msg = "" if ok else (data.get("result") or ("".join(err_lines) or "\n".join(raw_lines[-3:])).strip()[-600:]
                         or f"Claude Code stopped (exit {proc.returncode}).")
    data["_structured"] = schema is not None and "--json-schema" in h
    return ok, data, msg


def _log_tool_uses(ev: dict, log) -> None:
    """Turn Claude Code's tool calls into friendly log lines."""
    msg = ev.get("message") or {}
    for block in msg.get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name, inp = block.get("name", ""), block.get("input") or {}
        if name == "WebSearch":
            log(f"🔎 Searching: {str(inp.get('query', ''))[:90]}")
        elif name == "WebFetch":
            log(f"📄 Reading: {str(inp.get('url', ''))[:90]}")
        elif name == "Read":
            log(f"🖼 Looking at: {str(inp.get('file_path', '')).rsplit('/', 1)[-1][:60]}")


def _run(prompt: str, settings: dict, workdir: Path, tools: str, schema: dict | None, max_turns: int, log) -> dict:
    global _ISOLATION_OK
    exe = find_claude(settings.get("claude_code_path", ""))
    if not exe:
        raise RuntimeError("Claude Code isn't installed on this Mac. Re-run start.command to install it, "
                           "or install it from https://code.claude.com/docs/en/setup")
    token = clean_token(settings.get("claude_code_token"))
    if not token:
        raise RuntimeError("No Claude setup-token. In Terminal run:  claude setup-token  — then paste the token in Settings.")
    isolated = _ISOLATION_OK is not False
    ok, data, msg = _attempt(exe, prompt, settings, workdir, tools, schema, max_turns, isolated, token, log)
    if not ok and isolated and _not_logged_in(msg):
        log("Retrying Claude Code with plain settings…")
        ok, data, msg = _attempt(exe, prompt, settings, workdir, tools, schema, max_turns, False, token, log)
        if ok:
            _ISOLATION_OK = False
    elif ok and isolated:
        _ISOLATION_OK = True
    if not ok:
        low = msg.lower()
        if _not_logged_in(msg):
            msg = ("Claude Code didn't pick up your token. Check it starts with sk-ant-oat01- and was copied in full, "
                   "or create a fresh one with  claude setup-token . " + msg[:160])
        elif "401" in low or "invalid" in low or "expired" in low or "unauthorized" in low:
            msg = "Your Claude setup-token was rejected (expired or wrong). Run  claude setup-token  again and paste the new token in Settings. " + msg[:200]
        elif "usage limit" in low or "rate limit" in low:
            msg = "Your Claude plan's usage limit is reached — try again later. " + msg[:200]
        raise RuntimeError(f"Claude Code: {msg}")
    return data


def test_connection(settings: dict, workdir: Path) -> str:
    """Tiny round-trip used by the Settings "Test connection" button."""
    data = _run("Reply with exactly the word OK and nothing else.", settings, workdir, "", None, 2, lambda m: None)
    return (data.get("result") or "").strip()[:200]


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
