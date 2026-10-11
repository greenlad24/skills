"""Send files from a phone to this computer over Wi-Fi with a QR code.

The Mac shows a QR code with a secret link (expires after 12 h). The phone opens a tiny
Thai upload page and sends clips / narration straight into one product — original
quality, no cloud, no cables. Everything else in the app stays private to this computer.
"""

from __future__ import annotations

import base64
import io
import secrets
import socket
import time

TOKEN_TTL = 12 * 3600
_TOKENS: dict = {}   # token → (project_id, expires_at)


def lan_ip() -> str:
    """This computer's address on the local network (no traffic is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def new_token(pid: str) -> str:
    now = time.time()
    for t, (_, exp) in list(_TOKENS.items()):
        if exp < now:
            _TOKENS.pop(t, None)
    for t, (p, exp) in _TOKENS.items():   # reuse a live link for the same product
        if p == pid and exp - now > 3600:
            return t
    t = secrets.token_urlsafe(16)
    _TOKENS[t] = (pid, now + TOKEN_TTL)
    return t


def project_for(token: str) -> str | None:
    item = _TOKENS.get(token or "")
    if not item or item[1] < time.time():
        return None
    return item[0]


def qr_data_uri(url: str) -> str:
    import qrcode
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


PAGE = """<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ส่งไฟล์ · Thai TikTok Studio</title>
<style>
body{margin:0;background:#0f0f12;color:#f3f3f6;font:17px/1.5 -apple-system,Roboto,"Noto Sans Thai",sans-serif;padding:18px}
h1{font-size:21px;margin:0 0 4px}.muted{color:#9a9aab;font-size:14px}
.btn{display:block;width:100%;padding:18px;margin:14px 0 6px;border:0;border-radius:16px;font-size:19px;font-weight:700;color:#fff}
.clips{background:#fe2c55}.voice{background:#1f6f6b}
.list{margin-top:14px}.f{background:#1d1d24;border-radius:12px;padding:10px 12px;margin:8px 0;font-size:14px}
.bar{height:8px;background:#2a2a35;border-radius:8px;overflow:hidden;margin-top:6px}.bar i{display:block;height:100%;background:#22c55e;width:0}
.ok{color:#6ee7a0}.bad{color:#fca5a5}
</style></head><body>
<h1>📱 ส่งไฟล์ไปที่ Mac</h1>
<div class="muted">สินค้า: <b>{name}</b><br>มือถือกับ Mac ต้องต่อ Wi‑Fi เดียวกัน · อย่าปิดหน้านี้ระหว่างส่ง</div>
<button class="btn clips" onclick="pick('footage')">🎬 เลือกคลิป / รูป</button>
<div class="muted">เลือกได้หลายไฟล์พร้อมกัน ไม่ต้องตั้งชื่อ — ระบบจับคู่กับช็อตให้เอง</div>
<button class="btn voice" onclick="pick('narration')">🎙 เลือกเสียงพากย์</button>
<div class="muted">วิดีโอหรือไฟล์เสียงที่คุณอ่านสคริปต์ (คลิปละ 1 ไฟล์)</div>
<input type="file" id="inp" multiple hidden>
<div class="list" id="list"></div>
<script>
let kind = "footage";
const inp = document.getElementById("inp");
function pick(k){ kind = k; inp.accept = k === "narration" ? "video/*,audio/*" : "video/*,image/*"; inp.value = ""; inp.click(); }
inp.onchange = () => { [...inp.files].reduce((p, f) => p.then(() => send(f, kind)), Promise.resolve()); };
function send(f, k){
  return new Promise((done) => {
    const row = document.createElement("div"); row.className = "f";
    row.innerHTML = `<b></b> <span class="st muted">กำลังส่ง…</span><div class="bar"><i></i></div>`;
    row.querySelector("b").textContent = (k === "narration" ? "🎙 " : "🎬 ") + f.name;
    document.getElementById("list").prepend(row);
    const fd = new FormData(); fd.append("files", f, f.name); fd.append("kind", k);
    fd.append("mtimes", JSON.stringify([f.lastModified || 0]));
    const x = new XMLHttpRequest(); x.open("POST", location.pathname.replace(/\\/$/, "") + "/upload");
    x.upload.onprogress = (e) => { if (e.lengthComputable) row.querySelector("i").style.width = (e.loaded / e.total * 100) + "%"; };
    x.onload = () => { const ok = x.status < 400; row.querySelector(".st").className = "st " + (ok ? "ok" : "bad");
      row.querySelector(".st").textContent = ok ? "✓ ส่งแล้ว" : "✗ ส่งไม่สำเร็จ ลองใหม่"; done(); };
    x.onerror = () => { row.querySelector(".st").className = "st bad"; row.querySelector(".st").textContent = "✗ ส่งไม่สำเร็จ — เช็ก Wi‑Fi"; done(); };
    x.send(fd);
  });
}
</script></body></html>"""


def page(project_name: str) -> str:
    import html
    return PAGE.replace("{name}", html.escape(project_name or ""))
