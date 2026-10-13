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
# Listen on the local network so phones can send files (only the /m/<secret> pages are
# reachable from other devices — see require_login). Hosted mode sits behind a proxy.
HOST = os.environ.get("TTS_STUDIO_HOST", "0.0.0.0")
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

LOGIN_PAGE = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Thai TikTok Studio · {title}</title><link rel="stylesheet" href="/static/style.css"></head>
<body class="login-page">
<header class="topbar"><span class="brand"><span class="logo" aria-hidden="true">▶</span><span class="brand-name">TikTok Studio</span></span>
<div class="top-right"><label class="lang-wrap"><span aria-hidden="true">🌐</span>
<select id="langSel" class="lang-sel" aria-label="ภาษา / Language"><option value="th"{th_sel}>ไทย</option><option value="en"{en_sel}>English</option></select></label></div></header>
<div class="login-wrap"><form method="post" action="/login?lang={lang}" class="card login-card">
<h1><span class="logo" aria-hidden="true">▶</span> {title}</h1><p class="muted">{sub}</p>
<label for="pw">{password}</label><input id="pw" type="password" name="password" autofocus autocomplete="current-password" placeholder="{password}">{err}
<div class="row"><button class="btn primary big wide">{button}</button></div></form></div>
<script>
document.getElementById("langSel").onchange = function (e) {
  var l = e.target.value;
  try { localStorage.setItem("tts_lang", l); } catch (x) {}
  document.cookie = "tts_lang=" + l + ";path=/;max-age=31536000;samesite=lax";
  location.href = "/login?lang=" + l;
};
(function () {  // follow the language picked earlier in this browser
  try { var l = localStorage.getItem("tts_lang");
    if (l && l !== "{lang}" && location.search.indexOf("lang=") < 0) location.replace("/login?lang=" + l); } catch (x) {}
})();
</script></body></html>"""


def _ui_lang() -> str:
    from . import ui_text
    return ui_text.pick_lang(request.args.get("lang"), request.cookies.get("tts_lang"),
                             config.load_settings().get("language"))


def _login_page(err: bool = False) -> str:
    from . import ui_text
    lang = _ui_lang()
    tx = ui_text.texts(lang, "login.")
    html = LOGIN_PAGE
    for k in ("title", "sub", "password", "button"):
        html = html.replace("{" + k + "}", tx[k])
    return (html.replace("{lang}", lang).replace("{th_sel}", " selected" if lang == "th" else "")
            .replace("{en_sel}", " selected" if lang == "en" else "")
            .replace("{err}", f'<p class="banner bad small" role="alert">{tx["wrong"]}</p>' if err else ""))


LOCAL_ADDRS = ("127.0.0.1", "::1", "::ffff:127.0.0.1")


@app.before_request
def require_login():
    if request.path.startswith("/m/") or request.path.startswith("/pub/"):  # secret-link pages
        return None
    if not SERVER_MODE and request.remote_addr not in LOCAL_ADDRS:
        abort(403)                               # the full app is only for this computer
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
    if request.method == "POST":
        if hmac.compare_digest((request.form.get("password") or "").encode(), PASSWORD.encode()):
            session.permanent = True
            session["ok"] = True
            return redirect("/")
        return _login_page(err=True)
    return _login_page()


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


@app.get("/api/update")
def update_status():
    from . import updater
    updater.check_soon()
    return jsonify(dict(updater.STATE, enabled=updater.enabled()))


@app.post("/api/update/check")
def update_check():
    from . import updater
    if updater.enabled():
        with updater._LOCK:
            updater.check_and_download()
    return jsonify(dict(updater.STATE, enabled=updater.enabled()))


@app.post("/api/update/restart")
def update_restart():
    from . import updater
    if not updater.restart():
        return jsonify({"error": "Close the app and open it again to finish the update."}), 400
    return jsonify({"ok": True})


@app.get("/api/style")
def style_get():
    from .editor import reference
    return jsonify(dict(reference.load(), has_frames=bool(reference.sheet_path())))


@app.post("/api/style")
def style_upload():
    """Upload a reference video you liked — its pacing becomes the editor's style."""
    from .editor import media, reference
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Choose a video file."}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in media.VIDEO_EXT:
        return jsonify({"error": "That file is not a video."}), 400
    dest = reference.style_dir() / f"reference{ext}"
    f.save(dest)
    try:
        prof = reference.save_reference(dest)
    except Exception as e:  # unreadable video
        dest.unlink(missing_ok=True)
        return jsonify({"error": f"Couldn't read that video ({e})."}), 400
    return jsonify(dict(prof, has_frames=bool(reference.sheet_path())))


@app.delete("/api/style")
def style_reset():
    from .editor import reference
    return jsonify(dict(reference.reset(), has_frames=False))


@app.get("/api/settings")
def get_settings():
    return jsonify(config.public_settings(config.load_settings()))


@app.post("/api/settings")
def set_settings():
    data = request.get_json(force=True) or {}
    for k in ("anthropic_api_key", "openai_api_key", "claude_code_token", "postpeer_key",
              "cloudinary_url"):  # masked values from the UI = unchanged
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
        "edits": service.list_edits(pid),
        "product_images": [p.name for p in sorted((d / "product_images").glob("*"))],
        "jobs": jobs.for_project(pid),
        "folder": str(d),
    }
    return jsonify(out)


@app.delete("/api/projects/<pid>")
def delete_project(pid):
    from . import scheduler
    scheduler.cancel_project(pid, config.load_settings())   # don't leave posts for deleted videos
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


@app.post("/api/projects/<pid>/phone-link")
def phone_link(pid):
    from . import phone
    projects.pdir(pid)
    token = phone.new_token(pid)
    host = request.host if SERVER_MODE else f"{phone.lan_ip()}:{PORT}"
    scheme = "https" if SERVER_MODE else "http"
    url = f"{scheme}://{host}/m/{token}"
    return jsonify({"url": url, "qr": phone.qr_data_uri(url), "hours": phone.TOKEN_TTL // 3600})


@app.get("/m/<token>")
def phone_page(token):
    from . import phone
    pid = phone.project_for(token)
    lang = _ui_lang()
    if not pid:
        return phone.expired_page(lang), 404
    return phone.page(projects.meta(pid).get("name", ""), lang, website=SERVER_MODE)


@app.post("/m/<token>/upload")
def phone_upload(token):
    from . import phone
    pid = phone.project_for(token)
    if not pid:
        return jsonify({"error": "Link expired"}), 404
    return upload(pid)


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
    if _busy(pid):
        return jsonify({"error": "A render is already running for this product."}), 409
    job = jobs.start("render", pid, service.render_videos, pid, data.get("videos") or [], config.load_settings(),
                     bool(data.get("draft")), int(data.get("versions") or 1))
    return jsonify({"job": job.to_dict()})


def _busy(pid):
    return any(j["kind"] in ("render", "prepare") and j["status"] == "running" for j in jobs.for_project(pid))


@app.post("/api/projects/<pid>/prepare")
def prepare_edits(pid):
    """Review step 1: plan every video + quick previews (nothing final is rendered yet)."""
    data = request.get_json(force=True) or {}
    if _busy(pid):
        return jsonify({"error": "A render is already running for this product."}), 409
    job = jobs.start("prepare", pid, service.prepare_edits, pid, data.get("videos") or [], config.load_settings(),
                     int(data.get("versions") or 1))
    return jsonify({"job": job.to_dict()})


@app.get("/api/projects/<pid>/edits")
def list_edits(pid):
    return jsonify({"edits": service.list_edits(pid)})


@app.post("/api/projects/<pid>/edits/<key>")
def update_edit(pid, key):
    data = request.get_json(force=True) or {}
    try:
        return jsonify({"edit": service.update_edit(pid, key, data.get("stickers") or [])})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.get("/api/projects/<pid>/edits/<key>/frame")
def edit_frame(pid, key):
    try:
        f = service.edit_frame(pid, key, float(request.args.get("t", 0)))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return send_file(f, mimetype="image/jpeg", max_age=3600)


@app.post("/api/projects/<pid>/edits/<key>/preview")
def preview_edit(pid, key):
    if _busy(pid):
        return jsonify({"error": "A render is already running for this product."}), 409
    job = jobs.start("prepare", pid, service.preview_edit, pid, key, config.load_settings())
    return jsonify({"job": job.to_dict()})


@app.post("/api/projects/<pid>/render-final")
def render_final(pid):
    data = request.get_json(force=True) or {}
    if _busy(pid):
        return jsonify({"error": "A render is already running for this product."}), 409
    job = jobs.start("render", pid, service.render_final, pid, data.get("keys") or [], config.load_settings())
    return jsonify({"job": job.to_dict()})


@app.post("/api/projects/<pid>/renders/delete")
def delete_renders(pid):
    data = request.get_json(force=True) or {}
    return jsonify(service.delete_renders(pid, data.get("names") or []))


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


# ---------------------------------------------------------------- Tool 3: scheduler
def _sched_settings():
    return config.load_settings()


@app.get("/api/schedule")
def schedule_get():
    from . import scheduler
    data = scheduler.load()
    posts = sorted(data["posts"], key=lambda p: p["at"])
    taken = {(p["project_id"], p["render"]) for p in posts if p["status"] != "cancelled"}
    ready = [v for v in scheduler.finished_videos() if (v["project_id"], v["render"]) not in taken]
    st = _sched_settings()
    return jsonify({"posts": [dict(p, text=scheduler.full_text(p)) for p in posts], "ready": ready,
                    "slots": scheduler.SLOTS, "now": scheduler._fmt(scheduler.now_bkk()),
                    "connected": bool(st.get("postpeer_key") and st.get("postpeer_account_id")),
                    "hosting": "website" if st.get("public_base_url") else
                               "cloudinary" if st.get("cloudinary_url") else "litterbox"})


@app.post("/api/schedule/auto")
def schedule_auto():
    from . import scheduler
    per_day = int((request.get_json(silent=True) or {}).get("per_day") or _sched_settings().get("posts_per_day", 1))
    config.save_settings({"posts_per_day": per_day})
    created = scheduler.auto_schedule(per_day)
    threading.Thread(target=scheduler.tick, args=(_sched_settings(),), daemon=True).start()
    return jsonify({"created": len(created)})


@app.patch("/api/schedule/<post_id>")
def schedule_edit(post_id):
    from . import scheduler
    d = request.get_json(force=True) or {}
    p = scheduler.edit(post_id, d.get("at"), d.get("caption"), d.get("hashtags"), _sched_settings())
    if not p:
        abort(404)
    return jsonify(p)


@app.post("/api/schedule/<post_id>/caption")
def schedule_caption(post_id):
    from . import scheduler
    p = next((x for x in scheduler.load()["posts"] if x["id"] == post_id), None)
    if not p:
        abort(404)
    variant = int((request.get_json(silent=True) or {}).get("variant") or 1)
    plan = projects.load_json(projects.pdir(p["project_id"]) / "plan.json") or {"videos": [], "research": {}}
    video = next((v for v in plan["videos"] if v["id"] == p["video_id"]), {})
    cap = scheduler.make_caption(video, plan.get("research", {}), variant)
    return jsonify(scheduler.edit(post_id, caption=cap["caption"], hashtags=cap["hashtags"], settings=_sched_settings()))


@app.post("/api/schedule/<post_id>/post-now")
def schedule_post_now(post_id):
    from . import scheduler
    try:
        return jsonify(scheduler.submit(post_id, _sched_settings(), now_=True))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.delete("/api/schedule/<post_id>")
def schedule_cancel(post_id):
    from . import scheduler
    try:
        return jsonify(scheduler.cancel(post_id, _sched_settings()) or {})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/schedule/sync")
def schedule_sync():
    from . import scheduler
    scheduler.tick(_sched_settings())
    return jsonify({"ok": True})


@app.post("/api/claude-code/test")
def claude_code_test():
    """Settings → "Test connection" for the Claude-account mode (can test a token before saving)."""
    from . import llm_claude_code
    st = dict(config.load_settings())
    tok = ((request.get_json(silent=True) or {}).get("token") or "").strip()
    if tok and not tok.startswith("•"):
        st["claude_code_token"] = tok
    try:
        reply = llm_claude_code.test_connection(st, config.HOME)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "reply": reply})


@app.post("/api/postpeer/connect")
def postpeer_connect():
    from . import postpeer
    try:
        return jsonify({"url": postpeer.connect_url(_sched_settings().get("postpeer_key", ""))})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.get("/api/postpeer/accounts")
def postpeer_accounts():
    from . import postpeer
    try:
        accts = postpeer.accounts(_sched_settings().get("postpeer_key", ""))
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"accounts": [a for a in accts if not a["platform"] or "tiktok" in a["platform"]]})


@app.post("/api/cloudinary/check")
def cloudinary_check():
    from . import cloudinary_host
    try:
        return jsonify(cloudinary_host.check(_sched_settings().get("cloudinary_url", "")))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.get("/pub/<token>/<name>")
def public_video(token, name):
    """Hosted website only: PostPeer fetches the final video from this secret link."""
    from . import scheduler
    for p in scheduler.load()["posts"]:
        if p.get("pub_token") == token and p["render"] == name and p["status"] in ("planned", "queued", "posted"):
            f = projects.pdir(p["project_id"]) / "renders" / p["render"]
            if f.exists():
                return send_file(f, mimetype="video/mp4", conditional=True)
    abort(404)


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
    from . import scheduler
    scheduler.start_worker(config.load_settings)
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
