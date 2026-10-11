"""The Claude-subscription provider, driven against a fake `claude` CLI."""

import json
import os
import stat
import sys

import pytest
from fixtures import sample_plan

from studio import llm_claude_code

FAKE = r'''#!{py}
import json, os, sys
args = sys.argv[1:]
if args == ["--help"]:
    print("--tools --json-schema --safe-mode --no-session-persistence --permission-prompts --allowedTools")
    sys.exit(0)
if args == ["--version"]:
    print("2.9.0 (Claude Code)"); sys.exit(0)
log = {"args": args, "stdin": sys.stdin.read(), "token": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"),
       "api_key": os.environ.get("ANTHROPIC_API_KEY"), "cwd": os.getcwd()}
open(os.environ["FAKE_LOG"], "a").write(json.dumps(log) + "\n")
if os.environ.get("FAKE_SAFE_BREAKS") and "--safe-mode" in args:
    print(json.dumps({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})); sys.exit(1)
if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") != "sk-ant-oat01-good":
    print(json.dumps({"type": "result", "is_error": True, "result": "Invalid API key · 401 authentication_error"})); sys.exit(1)
if "--json-schema" in args:
    print(json.dumps({"type": "result", "is_error": False, "result": "", "structured_output": json.load(open(os.environ["FAKE_PLAN"]))}))
else:
    print(json.dumps({"type": "result", "is_error": False, "result": "DOSSIER: soft mattress, 5ft"}))
'''


@pytest.fixture()
def fake_claude(tmp_path, monkeypatch):
    exe = tmp_path / "claude"
    exe.write_text(FAKE.replace("{py}", sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "plan.json").write_text(json.dumps(sample_plan(), ensure_ascii=False))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("FAKE_PLAN", str(tmp_path / "plan.json"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api-should-not-be-used")
    llm_claude_code._help.cache_clear()
    llm_claude_code._ISOLATION_OK = None
    return exe, tmp_path


def _settings(exe, token="sk-ant-oat01-good"):
    return {"claude_code_path": str(exe), "claude_code_token": token, "claude_model": "claude-opus-5-5",
            "videos_per_product": 2}


def test_research_and_plan_use_subscription_token(fake_claude):
    exe, tmp = fake_claude
    shot = tmp / "shot.png"
    shot.write_bytes(b"png")
    g = {"input_text": "ที่นอน", "user_images": [str(shot)], "product_images": []}
    dossier = llm_claude_code.research(g, _settings(exe), log=lambda m: None, workdir=tmp)
    assert dossier.startswith("DOSSIER")
    plan = llm_claude_code.make_plan(g, dossier, _settings(exe), log=lambda m: None, workdir=tmp)
    assert plan["videos"][0]["id"] == "V1"
    calls = [json.loads(l) for l in (tmp / "log.jsonl").read_text().splitlines()]
    for c in calls:
        assert c["token"] == "sk-ant-oat01-good" and c["api_key"] is None   # API key removed → plan is billed
        assert "--safe-mode" in c["args"] and "--no-session-persistence" in c["args"]
        assert "Edit,Write,Bash,NotebookEdit" in c["args"]
        assert c["cwd"] == str(tmp)
    assert "WebSearch,WebFetch,Read" in calls[0]["args"] and str(shot.resolve()) in calls[0]["stdin"]
    assert "--json-schema" in calls[1]["args"]


def test_bad_token_gives_clear_message(fake_claude):
    exe, tmp = fake_claude
    with pytest.raises(RuntimeError, match="setup-token was rejected"):
        llm_claude_code.research({"input_text": "x"}, _settings(exe, "sk-ant-oat01-old"), log=lambda m: None, workdir=tmp)


def test_planner_end_to_end_with_claude_code(fake_claude, monkeypatch):
    exe, tmp = fake_claude
    monkeypatch.setenv("TTS_STUDIO_HOME", str(tmp / "home"))
    import importlib

    import studio.config as config
    importlib.reload(config)
    import studio.projects as projects
    importlib.reload(projects)
    import studio.planner as planner
    importlib.reload(planner)
    monkeypatch.setattr(planner.scrape, "gather", lambda text, imgs, d, log=print: {
        "input_text": text, "url": "", "page": {}, "search_results": [], "product_images": [], "user_images": []})

    class J:
        progress = 0
        def say(self, m): pass
    pid = projects.new_project("ที่นอน")["id"]
    res = planner.run_planning(J(), pid, "ที่นอน", [], "", {**_settings(exe), "provider": "claude_code"})
    assert res == {"videos": 2}
    assert projects.meta(pid)["status"] == "planned"


def test_not_logged_in_with_safe_mode_falls_back(fake_claude, monkeypatch):
    """The real-world failure: this Claude Code build ignores the token under --safe-mode."""
    exe, tmp = fake_claude
    monkeypatch.setenv("FAKE_SAFE_BREAKS", "1")
    st = _settings(exe, "sk-ant-oat01-\n  good")            # wrapped copy from Terminal
    assert llm_claude_code.test_connection(st, tmp)          # works after the automatic retry
    assert llm_claude_code._ISOLATION_OK is False
    calls = [json.loads(l) for l in (tmp / "log.jsonl").read_text().splitlines()]
    assert "--safe-mode" in calls[0]["args"] and "--safe-mode" not in calls[1]["args"]
    assert calls[1]["token"] == "sk-ant-oat01-good"
    llm_claude_code.research({"input_text": "x"}, st, log=lambda m: None, workdir=tmp)
    calls = [json.loads(l) for l in (tmp / "log.jsonl").read_text().splitlines()]
    assert len(calls) == 3 and "--safe-mode" not in calls[2]["args"]   # remembered: no wasted retry


def test_not_logged_in_message_is_clear(fake_claude, monkeypatch):
    exe, tmp = fake_claude
    monkeypatch.setenv("FAKE_SAFE_BREAKS", "1")
    monkeypatch.setattr(llm_claude_code, "_attempt", lambda *a, **k: (False, {}, "Not logged in · Please run /login"))
    with pytest.raises(RuntimeError, match="didn't pick up your token"):
        llm_claude_code.test_connection(_settings(exe), tmp)
