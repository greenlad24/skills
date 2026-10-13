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


PAGE = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{title} · Thai TikTok Studio</title>
<link rel="icon" href="data:,">
<style>
*{box-sizing:border-box}
body{margin:0;background:#f3f4f8;color:#14141c;font:17px/1.6 -apple-system,Roboto,"Noto Sans Thai","Sukhumvit Set",sans-serif}
.top{position:sticky;top:0;z-index:5;display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 12px;background:rgba(255,255,255,.96);border-bottom:1px solid #e2e4ec}
.brand{display:flex;align-items:center;gap:8px;font-weight:800}
.logo{width:34px;height:34px;border-radius:10px;display:inline-flex;align-items:center;justify-content:center;color:#fff;background:linear-gradient(135deg,#25f4ee,#fe2c55 70%)}
.lang{display:inline-flex;align-items:center;gap:4px;background:#f7f8fb;border:1px solid #e2e4ec;border-radius:999px;padding:0 6px 0 12px;height:44px}
.lang select{border:0;background:transparent;font-family:inherit;font-weight:700;font-size:16px;height:42px;color:#14141c}
.wrap{padding:16px;max-width:560px;margin:0 auto}
h1{font-size:23px;line-height:1.3;margin:4px 0 6px}.muted{color:#5b5e6e;font-size:15px}
.card{background:#fff;border:1px solid #e2e4ec;border-radius:18px;padding:16px;margin:14px 0}
.btn{display:block;width:100%;min-height:60px;padding:16px;margin:0 0 8px;border:0;border-radius:16px;font-family:inherit;font-weight:700;font-size:19px;color:#fff;cursor:pointer}
.clips{background:#e3164a;box-shadow:0 4px 14px rgba(227,22,74,.28)}.voice{background:#0b7a76}
.btn:active{transform:scale(.98)}
.list{margin-top:8px}.f{background:#fff;border:1px solid #e2e4ec;border-radius:14px;padding:10px 12px;margin:8px 0;font-size:15px;word-break:break-all}
.bar{height:10px;background:#eceef4;border-radius:10px;overflow:hidden;margin-top:6px}.bar i{display:block;height:100%;background:linear-gradient(90deg,#25c2bd,#e3164a);width:0;transition:width .3s}
.ok{color:#147a45;font-weight:700}.bad{color:#c21c1c;font-weight:700}
.done{background:#e3f6ec;color:#0f5f3a;border-radius:14px;padding:12px 14px;font-weight:700;display:none}
</style></head><body>
<header class="top"><span class="brand"><span class="logo" aria-hidden="true">▶</span>TikTok Studio</span>
<label class="lang"><span aria-hidden="true">🌐</span><select id="lang" aria-label="ภาษา / Language"><option value="th">ไทย</option><option value="en">English</option></select></label></header>
<div class="wrap">
<h1 data-k="{title_key}">{title}</h1>
<div class="muted"><span data-k="product">{product}</span> <b>{name}</b><br>{wifi_html}</div>
<div class="card"><button class="btn clips" onclick="pick('footage')" data-k="clips">{clips}</button>
<div class="muted" data-k="clipsHint">{clipsHint}</div></div>
<div class="card"><button class="btn voice" onclick="pick('narration')" data-k="voice">{voice}</button>
<div class="muted" data-k="voiceHint">{voiceHint}</div></div>
<div class="done" id="done" role="status" data-k="allDone">{allDone}</div>
<input type="file" id="inp" multiple hidden>
<div class="list" id="list" aria-live="polite"></div></div>
<script>
var T = {dicts};
var lang = "{lang}";
try { var q = new URLSearchParams(location.search).get("lang"); var s = localStorage.getItem("tts_lang");
  if (!q && (s === "th" || s === "en")) lang = s; } catch (e) {}
function tr(k) { return (T[lang] && T[lang][k]) || T.th[k] || k; }
function apply() {
  document.documentElement.lang = lang; document.getElementById("lang").value = lang;
  document.querySelectorAll("[data-k]").forEach(function (el) { el.textContent = tr(el.getAttribute("data-k")); });
  document.querySelectorAll(".st").forEach(function (el) { el.textContent = tr(el.getAttribute("data-s")); });
}
document.getElementById("lang").onchange = function (e) { lang = e.target.value; try { localStorage.setItem("tts_lang", lang); } catch (x) {} apply(); };
apply();
var kind = "footage", pending = 0, sent = 0;
var inp = document.getElementById("inp");
function pick(k){ kind = k; inp.accept = k === "narration" ? "video/*,audio/*" : "video/*,image/*"; inp.value = ""; inp.click(); }
inp.onchange = function () { var fs = Array.prototype.slice.call(inp.files); pending += fs.length; document.getElementById("done").style.display = "none";
  fs.reduce(function (p, f) { return p.then(function () { return send(f, kind); }); }, Promise.resolve()); };
function setSt(row, key, cls) { var st = row.querySelector(".st"); st.setAttribute("data-s", key); st.className = "st " + cls; st.textContent = tr(key); }
function send(f, k){
  return new Promise(function (done) {
    var row = document.createElement("div"); row.className = "f";
    row.innerHTML = '<b></b> <span class="st muted"></span><div class="bar"><i></i></div>';
    row.querySelector("b").textContent = (k === "narration" ? "🎙 " : "🎬 ") + f.name;
    setSt(row, "sending", "muted");
    document.getElementById("list").prepend(row);
    var fd = new FormData(); fd.append("files", f, f.name); fd.append("kind", k);
    fd.append("mtimes", JSON.stringify([f.lastModified || 0]));
    var x = new XMLHttpRequest(); x.open("POST", location.pathname.replace(/\\/$/, "") + "/upload");
    x.upload.onprogress = function (e) { if (e.lengthComputable) row.querySelector("i").style.width = (e.loaded / e.total * 100) + "%"; };
    var fin = function (ok, key) { setSt(row, key, ok ? "ok" : "bad"); pending--; if (ok) sent++;
      if (!pending && sent) document.getElementById("done").style.display = "block"; done(); };
    x.onload = function () { fin(x.status < 400, x.status < 400 ? "sent" : "failed"); };
    x.onerror = function () { fin(false, "failedWifi"); };
    x.send(fd);
  });
}
</script></body></html>"""

EXPIRED = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Thai TikTok Studio</title></head><body style="margin:0;background:#f3f4f8;font:18px/1.6 -apple-system,Roboto,'Noto Sans Thai',sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px;text-align:center;color:#14141c">
<div><div style="font-size:56px">⏰</div><h2>{msg}</h2></div></body></html>"""


def _texts(lang: str) -> dict:
    from . import ui_text
    return ui_text.texts(lang, "phonepage.")


def page(project_name: str, lang: str = "th", website: bool = False) -> str:
    import html
    import json
    tx = _texts(lang)
    title_key = "titleWeb" if website else "title"
    dicts = json.dumps({lg: _texts(lg) for lg in ("th", "en")}, ensure_ascii=False).replace("</", "<\\/")
    out = PAGE
    for k in ("product", "clips", "clipsHint", "voice", "voiceHint", "allDone"):
        out = out.replace("{" + k + "}", html.escape(tx[k]))
    wifi = "" if website else f'<span data-k="wifi">{html.escape(tx["wifi"])}</span>'
    return (out.replace("{title_key}", title_key).replace("{title}", html.escape(tx[title_key]))
            .replace("{wifi_html}", wifi).replace("{lang}", lang).replace("{dicts}", dicts)
            .replace("{name}", html.escape(project_name or "")))


def expired_page(lang: str = "th") -> str:
    import html
    return EXPIRED.replace("{lang}", lang).replace("{msg}", html.escape(_texts(lang)["expired"]))


CAPTIONS_PAGE = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
body{{margin:0;font-family:-apple-system,"Sukhumvit Set","Noto Sans Thai",sans-serif;background:#f4f4f6;color:#111}}
header{{padding:18px 16px 6px}}h1{{font-size:22px;margin:0 0 4px}}p.sub{{margin:0;color:#666;font-size:15px}}
.card{{background:#fff;margin:12px 16px;border-radius:18px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.card.done{{opacity:.5}}.when{{font-weight:700;font-size:17px}}.title{{color:#555;font-size:14px;margin:2px 0 8px}}
textarea{{width:100%;box-sizing:border-box;border:1px solid #ddd;border-radius:12px;padding:10px;font-size:16px;min-height:120px;font-family:inherit}}
button{{width:100%;margin-top:8px;border:0;border-radius:14px;padding:16px;font-size:18px;font-weight:700;background:#e11d48;color:#fff}}
button.ok{{background:#10b981}}.mark{{background:#eee;color:#333;font-size:15px;padding:10px}}
.steps{{margin:8px 16px;padding:12px 14px 12px 32px;background:#fff7ed;border-radius:14px;font-size:15px}}
.empty{{text-align:center;color:#777;padding:40px 16px}}
</style></head><body>
<header><h1>{title}</h1><p class="sub">{sub}</p></header>
<ol class="steps">{steps}</ol>
{cards}
<script>
function copy(i){{var t=document.getElementById('t'+i);t.focus();t.select();t.setSelectionRange(0,99999);
var ok=false;try{{ok=document.execCommand('copy')}}catch(e){{}}
if(!ok&&navigator.clipboard){{navigator.clipboard.writeText(t.value)}}
var b=document.getElementById('b'+i);b.textContent='{copied}';b.className='ok';setTimeout(function(){{b.textContent='{copy}';b.className=''}},2500)}}
function mark(i,id){{var c=document.getElementById('c'+i);c.classList.toggle('done');
try{{var d=JSON.parse(localStorage.getItem('doneCaps')||'{{}}');d[id]=c.classList.contains('done');localStorage.setItem('doneCaps',JSON.stringify(d))}}catch(e){{}}}}
try{{var d=JSON.parse(localStorage.getItem('doneCaps')||'{{}}');document.querySelectorAll('.card').forEach(function(c){{if(d[c.dataset.id])c.classList.add('done')}})}}catch(e){{}}
</script></body></html>"""

CAP_TEXT = {
    "th": {"title": "📋 แคปชันสำหรับโพสต์", "sub": "คัดลอกไปวางใน TikTok ตอนโพสต์จากกล่องข้อความ",
           "steps": ["เปิด TikTok → กล่องข้อความ (หรือ ฉบับร่าง) แตะคลิปที่ส่งมา", "กด คัดลอก ด้านล่าง แล้ววางในช่องคำบรรยาย",
                     "เพิ่มตะกร้าสินค้า แล้วกด โพสต์"],
           "copy": "📋 คัดลอกแคปชัน", "copied": "✓ คัดลอกแล้ว — ไปวางใน TikTok ได้เลย", "mark": "✓ โพสต์อันนี้แล้ว",
           "empty": "ยังไม่มีโพสต์ที่ส่งไป TikTok"},
    "en": {"title": "📋 Captions to post", "sub": "Copy them into TikTok when you post from your inbox",
           "steps": ["Open TikTok → Inbox (or Drafts) and tap the video that arrived", "Tap Copy below and paste into the description",
                     "Add the product basket and tap Post"],
           "copy": "📋 Copy caption", "copied": "✓ Copied — paste it in TikTok", "mark": "✓ I posted this one",
           "empty": "No posts sent to TikTok yet"},
}


def captions_page(posts: list, lang: str) -> str:
    import html
    T = CAP_TEXT.get(lang, CAP_TEXT["th"])
    cards = []
    for i, p in enumerate(posts):
        cards.append(
            f'<div class="card" id="c{i}" data-id="{html.escape(p["id"])}"><div class="when">🕒 {html.escape(p["when"])}</div>'
            f'<div class="title">{html.escape(p["title"])}</div>'
            f'<textarea id="t{i}" readonly>{html.escape(p["text"])}</textarea>'
            f'<button id="b{i}" onclick="copy({i})">{T["copy"]}</button>'
            f'<button class="mark" onclick="mark({i},\'{html.escape(p["id"])}\')">{T["mark"]}</button></div>')
    return CAPTIONS_PAGE.format(lang=lang, title=T["title"], sub=T["sub"],
                                steps="".join(f"<li>{s}</li>" for s in T["steps"]),
                                cards="".join(cards) or f'<p class="empty">{T["empty"]}</p>',
                                copy=T["copy"], copied=T["copied"])
