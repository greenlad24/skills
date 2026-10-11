"""Local web app (Flask). Run:  python -m studio.app   → http://127.0.0.1:8765"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import hmac
import secrets

from flask import Flask, abort, jsonify, redirect, request, send_file, send_from_directory, session
from werkzeug.utils import secure_filename

from . import __version__, config, jobs, planner, projects
from .editor import service
from .plan_schema import normalize_plan, plan_problems

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = None  # big video uploads are fine
PORT = int(os.environ.get("TTS_STUDIO_PORT", "8765"))
HOST = os.environ.get("TTS_STUDIO_HOST", "127.0.0.1")
SERVER_MODE = os.environ.get("TTS_STUDIO_SERVER") == "1"      # hosted on a website (no Finder, no auto-browser)
PASSWORD = os.environ.get("TTS_STUDIO_PASSWORD", "")          # required when hosted


def _secret_key() -> bytes:
    p = config.HOME / "secret.key"
    try:
        return p.read_bytes()
    except OSError:
        config.HOME.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        p.write_bytes(key)
        os.chmod(p, 0o600)
        return key


app.secret_key = _secret_key()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=SERVER_MODE, PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30)

LOGIN_PAGE = """<!doctype html><html lang="th"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Thai TikTok Studio · Login</title><link rel="stylesheet" href="/static/style.css">
<body style="display:flex;align-items:center;justify-content:center;min-height:100vh">
<form method="post" action="/login" class="card" style="width:min(380px,92vw)">
<h1>▶ Thai TikTok Studio</h1><p class="muted">ใส่รหัสผ่านเพื่อเข้าใช้งาน · Enter the password</p>
<input type="password" name="password" autofocus placeholder="รหัสผ่าน / password">{err}
<div class="row"><button class="primary wide">เข้าสู่ระบบ · Log in</button></div></form></body></html>"""


@app.before_request
def require_login():
    if not PASSWORD or request.path in ("/login",) or request.path.startswith("/static/"):
        return None
    if session.get("ok"):
        return None
    if request.path.startswith("/api/") or request.path.startswith("/files/"):
        return jsonify({"error": "Please log in again."}), 401
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if not PASSWORD:
        return redirect("/")
    err = ""
    if request.method == "POST":
        if hmac.compare_digest((request.form.get("password") or "").encode(), PASSWORD.encode()):
            session.permanent = True
            session["ok"] = True
            return redirect("/")
        err = '<p class="bad">รหัสผ่านไม่ถูกต้อง · Wrong password</p>'
    return LOGIN_PAGE.replace("{err}", err)


def _safe_name(name: str) -> str:
    # keep Thai letters; strip path parts and odd chars
    base = Path(name).name
    keep = "".join(c for c in base if c.isalnum() or c in "._- ()" or "฀" <= c <= "๿").strip()
    return keep or secure_filename(base) or "file"


def _unique(d: Path, name: str) -> Path:
    p = d / name
    stem, suf, i = p.stem, p.suffix, 2
    while p.exists():
        p = d / f"{stem} ({i}){suf}"
        i += 1
    return p


@app.errorhandler(FileNotFoundError)
def _not_found(e):
    return jsonify({"error": "Not found — it may have been deleted."}), 404


@app.errorhandler(ValueError)
def _bad_request(e):
    return jsonify({"error": str(e) or "Bad request"}), 400


@app.get("/")
def index():
    return send_from_directory(config.WEB_DIR, "index.html")


@app.get("/static/<path:name>")
def static_file(name):
    return send_from_directory(config.WEB_DIR, name)


@app.get("/api/health")
def health():
    from .editor import media, tts
    st = config.load_settings()
    try:
        ff = media.ffmpeg_exe()
    except RuntimeError:
        ff = ""
    from . import llm_claude_code
    exe = llm_claude_code.find_claude(st.get("claude_code_path", ""))
    return jsonify({"version": __version__, "ffmpeg": bool(ff), "tts": tts.available(st.get("tts_voice", "Kanya")),
                    "home": str(config.HOME), "platform": sys.platform, "server": SERVER_MODE,
                    "claude_code": bool(exe), "claude_code_version": llm_claude_code.version(exe) if exe else ""})


@app.get("/api/settings")
def get_settings():
    return jsonify(config.public_settings(config.load_settings()))


@app.post("/api/settings")
def set_settings():
    data = request.get_json(force=True) or {}
    for k in ("anthropic_api_key", "openai_api_key", "claude_code_token"):  # masked values = unchanged
        if str(data.get(k, "")).startswith("•"):
            data.pop(k)
    return jsonify(config.public_settings(config.save_settings(data)))


@app.post("/api/inspiration")
def import_inspiration():
    from . import inspiration
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "Choose a CSV file."}), 400
    raw = f.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp874", "replace")  # Thai Windows encoding
    n = inspiration.save_examples(text)
    if not n:
        return jsonify({"error": "No rows with Thai transcripts + play counts found."}), 400
    return jsonify({"examples": n})


@app.get("/api/inspiration")
def inspiration_status():
    from . import inspiration
    p = inspiration.EXAMPLES_PATH
    return jsonify({"exists": p.exists(), "preview": p.read_text("utf-8")[:1500] if p.exists() else ""})


@app.get("/api/projects")
def list_projects():
    return jsonify(projects.list_projects())


@app.post("/api/projects")
def create_project():
    text = (request.form.get("text") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    files = request.files.getlist("images")
    if not text and not files:
        return jsonify({"error": "Paste a product name or link, or attach a screenshot."}), 400
    meta = projects.new_project(text or "Screenshot product")
    pid = meta["id"]
    d = projects.pdir(pid)
    paths = []
    for f in files:
        if f and f.filename:
            p = _unique(d / "inputs", _safe_name(f.filename))
            f.save(p)
            paths.append(str(p))
    projects.save_json(d / "input.json", {"text": text, "notes": notes, "images": paths})
    job = jobs.start("plan", pid, planner.run_planning, pid, text, paths, notes, config.load_settings())
    return jsonify({"project": meta, "job": job.to_dict()})


@app.post("/api/projects/<pid>/replan")
def replan(pid):
    d = projects.pdir(pid)
    inp = projects.load_json(d / "input.json", {})
    job = jobs.start("plan", pid, planner.run_planning, pid, inp.get("text", ""), inp.get("images", []),
                     inp.get("notes", ""), config.load_settings())
    return jsonify({"job": job.to_dict()})


@app.get("/api/projects/<pid>")
def get_project(pid):
    try:
        d = projects.pdir(pid)
    except (FileNotFoundError, ValueError):
        abort(404)
    plan = projects.load_json(d / "plan.json")
    out = {
        "meta": projects.meta(pid),
        "input": projects.load_json(d / "input.json", {}),
        "plan": plan,
        "checks": projects.load_json(d / "checks.json", {}),
        "research_md": (d / "research.md").read_text("utf-8") if (d / "research.md").exists() else "",
        "manual_prompt": (d / "manual_prompt.txt").read_text("utf-8") if (d / "manual_prompt.txt").exists() else "",
        "files": service.file_infos(pid),
        "narration": service.file_infos(pid, "narration"),
        "assign": service.refresh_assign(pid, plan) if plan else service.load_assign(pid),
        "renders": service.list_renders(pid),
        "product_images": [p.name for p in sorted((d / "product_images").glob("*"))],
        "jobs": jobs.for_project(pid),
        "folder": str(d),
    }
    return jsonify(out)


@app.delete("/api/projects/<pid>")
def delete_project(pid):
    projects.delete_project(pid)
    return jsonify({"ok": True})


@app.post("/api/projects/<pid>/paste")
def paste_plan(pid):
    text = (request.get_json(force=True) or {}).get("text", "")
    try:
        res = planner.import_pasted(pid, text)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(res)


@app.post("/api/projects/<pid>/plan")
def save_plan(pid):
    """Save a plan edited in the UI (scripts, captions, durations…)."""
    raw = (request.get_json(force=True) or {}).get("plan")
    try:
        plan = normalize_plan(raw)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    d = projects.pdir(pid)
    projects.save_json(d / "plan.json", plan)
    from . import compliance, exports
    projects.save_json(d / "checks.json", {"warnings": plan_problems(plan), "compliance": compliance.check_plan(plan)})
    exports.write_all(d, plan, projects.meta(pid))
    return jsonify({"ok": True})


@app.post("/api/projects/<pid>/upload")
def upload(pid):
    sub = "narration" if request.form.get("kind") == "narration" else "footage"
    d = projects.pdir(pid) / sub
    d.mkdir(exist_ok=True)
    try:  # original "last modified" times from the browser (uploads otherwise get "now")
        mtimes = json.loads(request.form.get("mtimes") or "[]")
    except ValueError:
        mtimes = []
    saved = []
    for i, f in enumerate(request.files.getlist("files")):
        if f and f.filename:
            p = _unique(d, _safe_name(f.filename))
            f.save(p)
            if i < len(mtimes) and isinstance(mtimes[i], (int, float)) and mtimes[i] > 0:
                os.utime(p, (mtimes[i] / 1000, mtimes[i] / 1000))
            saved.append(p.name)
    plan = projects.load_json(projects.pdir(pid) / "plan.json")
    assign = service.refresh_assign(pid, plan) if plan else {}
    return jsonify({"saved": saved, "assign": assign})


@app.delete("/api/projects/<pid>/files/<name>")
def delete_file(pid, name):
    sub = "narration" if request.args.get("kind") == "narration" else "footage"
    p = projects.pdir(pid) / sub / _safe_name(name)
    if p.exists():
        p.unlink()
    return jsonify({"ok": True})


@app.post("/api/projects/<pid>/assign")
def set_assign(pid):
    data = request.get_json(force=True) or {}
    names = {i["name"] for i in service.file_infos(pid)}
    nar_names = {i["name"] for i in service.file_infos(pid, "narration")}
    assign = {
        "narration": {k: v for k, v in (data.get("narration") or {}).items() if v in nar_names},
        "shots": {k: v for k, v in (data.get("shots") or {}).items() if v in names},
        "vo": {k: v for k, v in (data.get("vo") or {}).items() if v in names},
        "music": [m for m in (data.get("music") or []) if m in names],
    }
    projects.save_json(projects.pdir(pid) / "assign.json", assign)
    return jsonify(assign)


@app.post("/api/projects/<pid>/render")
def render_videos(pid):
    data = request.get_json(force=True) or {}
    running = [j for j in jobs.for_project(pid) if j["kind"] == "render" and j["status"] == "running"]
    if running:
        return jsonify({"error": "A render is already running for this product."}), 409
    job = jobs.start("render", pid, service.render_videos, pid, data.get("videos") or [], config.load_settings(),
                     bool(data.get("draft")), int(data.get("versions") or 1))
    return jsonify({"job": job.to_dict()})


@app.get("/api/jobs/<jid>")
def job_status(jid):
    j = jobs.get(jid)
    if not j:
        abort(404)
    return jsonify(j.to_dict())


@app.post("/api/projects/<pid>/reveal")
def reveal(pid):
    if SERVER_MODE:
        return jsonify({"error": "Folders open only when the app runs on your own computer."}), 400
    d = projects.pdir(pid)
    sub = (request.get_json(silent=True) or {}).get("sub", "")
    target = d / sub if sub in ("footage", "narration", "renders") else d
    target.mkdir(exist_ok=True)
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    try:
        subprocess.Popen([opener, str(target)])
    except OSError:
        return jsonify({"error": f"Open this folder manually: {target}"}), 400
    return jsonify({"ok": True})


@app.get("/files/<pid>/<path:rel>")
def project_file(pid, rel):
    d = projects.pdir(pid).resolve()
    p = (d / rel).resolve()
    if d not in p.parents or not p.is_file():
        abort(404)
    return send_file(p, conditional=True, download_name=p.name,
                     as_attachment=request.args.get("download") == "1")


def main():
    config.ensure_dirs()
    if SERVER_MODE:
        if not PASSWORD:
            sys.exit("Refusing to start in server mode without TTS_STUDIO_PASSWORD (it protects your token and videos).")
        try:
            from waitress import serve
        except ImportError:
            sys.exit("Server mode needs waitress:  pip install waitress")
        print(f"Thai TikTok Studio (server mode) listening on {HOST}:{PORT}")
        serve(app, host=HOST, port=PORT, threads=8, max_request_body_size=50 * 1024 ** 3,
              channel_timeout=3600, cleanup_interval=60)
        return
    url = f"http://127.0.0.1:{PORT}"
    if os.environ.get("TTS_STUDIO_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"\n  Thai TikTok Studio is running → {url}\n  (keep this window open; close it to quit)\n")
    app.run(host=HOST, port=PORT, threaded=True, debug=False)


if __name__ == "__main__":
    main()
