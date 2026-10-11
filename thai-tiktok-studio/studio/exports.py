"""Human-friendly exports: printable Thai filming pack + scripts + edit summary."""

from __future__ import annotations

import html
from pathlib import Path

SIZE_TH = {
    "extreme_close_up": "โคลสอัพมาก (ECU)", "close_up": "โคลสอัพ (CU)", "medium": "ระยะกลาง (MS)",
    "wide": "ภาพกว้าง (WS)", "extreme_wide": "ภาพกว้างมาก (EWS)", "pov_hands": "มุมมองมือ (POV)",
    "overhead": "มุมบน (Top-down)", "selfie_talking": "พูดหน้ากล้อง", "screen_record": "อัดหน้าจอ",
    "product_photo": "รูปสินค้า",
}

CSS = """
body{font-family:'Kanit','Sukhumvit Set','Thonburi',sans-serif;margin:24px;color:#111;max-width:980px}
h1{margin:0 0 4px}h2{margin-top:36px;border-bottom:3px solid #fe2c55;padding-bottom:4px}
.meta{color:#555;font-size:14px}.pill{display:inline-block;background:#fff1c2;border-radius:99px;padding:2px 10px;margin:2px;font-size:13px}
table{border-collapse:collapse;width:100%;margin:10px 0}td,th{border:1px solid #ddd;padding:8px;vertical-align:top;font-size:14px}
th{background:#f5f5f5;text-align:left}.id{font-weight:700;white-space:nowrap;font-size:16px}
.script{white-space:pre-wrap;background:#fafafa;border-left:4px solid #25f4ee;padding:10px;font-size:15px}
.box{border:1px solid #eee;border-radius:8px;padding:10px;margin:8px 0}
@media print{h2{page-break-before:always}h2:first-of-type{page-break-before:auto}}
"""


def _e(s) -> str:
    return html.escape(str(s or ""))


def filming_pack_html(plan: dict, meta: dict) -> str:
    r = plan["research"]
    out = [f"<!doctype html><html lang='th'><meta charset='utf-8'><title>Filming pack — {_e(meta.get('name'))}</title>",
           f"<style>{CSS}</style><body>",
           f"<h1>🎬 แพ็กถ่ายทำ: {_e(r.get('product_name') or meta.get('name'))}</h1>",
           "<div class='meta'>" + " · ".join(_e(x) for x in (r.get("brand"), r.get("category"),
                                                              f"ราคา {r['price_thb']} บาท" if r.get("price_thb") else "") if x) + "</div>",
           "<div class='box'><b>ไม่ต้องตั้งชื่อไฟล์:</b> ถ่ายตามลำดับในรายการช็อต แล้วลากไฟล์ทั้งหมดใส่โปรแกรมตัดต่อ — "
           "ระบบจะจับคู่ให้อัตโนมัติตามเวลาที่ถ่ายและประเภทช็อต (ถ่ายซ้ำได้ เทคเกินจะถูกข้าม). "
           "ถ่ายแนวตั้ง 9:16 · ถ่ายเผื่อหัว-ท้ายช็อตละ 2–3 วินาที · แสงหน้าต่างหรือไฟวงแหวน · เช็ดเลนส์ก่อนถ่าย</div>"]
    for v in plan["videos"]:
        sc = v["score"]
        out.append(f"<h2>{_e(v['id'])} · อันดับ {v['rank']} · {_e(v['title_th'])}</h2>")
        out.append(f"<div class='meta'><span class='pill'>{_e(v['format'])}</span>"
                   f"<span class='pill'>hook: {_e(v['hook_type'])}</span>"
                   f"<span class='pill'>{_e(v['audio_mode'])}</span>"
                   f"<span class='pill'>~{v['target_length_sec']:.0f} วินาที</span>"
                   f"<span class='pill'>คะแนน {sc['total']:.0f}/100</span></div>")
        out.append(f"<p><b>Angle:</b> {_e(v['angle_en'])}<br><b>Why it works:</b> {_e(v['why_it_works_en'])}</p>")
        out.append(f"<h3>สคริปต์</h3><div class='script'>{_e(v['full_script_th'])}</div>")
        lines = [b["vo_th"] for b in v["timeline"] if b["vo_th"]]
        if v["audio_mode"] == "voiceover" and lines:
            out.append("<h3>🎙 อัดเสียงพากย์ (เสียงของคุณ)</h3><div class='box'>อ่านทุกบรรทัดต่อกันในเทคเดียว "
                       "เว้นจังหวะสั้นๆ (ประมาณครึ่งวินาที) ระหว่างบรรทัด · อัดในห้องเงียบ ถือมือถือห่างปากประมาณ 1 คืบ · "
                       "ไม่ต้องตั้งชื่อไฟล์ ระบบจะตัดแบ่งและวางเสียงให้ตรงภาพเอง<ol>"
                       + "".join(f"<li>{_e(l)}</li>" for l in lines) + "</ol></div>")
        out.append("<h3>รายการช็อตที่ต้องถ่าย</h3><table><tr><th>รหัส</th><th>ขนาดภาพ</th><th>ถ่ายอะไร</th>"
                   "<th>ถ่ายยังไง</th><th>บทพูด</th><th>ความยาว</th></tr>")
        for s in v["shots"]:
            out.append(f"<tr><td class='id'>{_e(s['id'])}</td><td>{_e(SIZE_TH.get(s['shot_size'], s['shot_size']))}</td>"
                       f"<td>{_e(s['what_to_film_th'])}</td><td>{_e(s['how_to_film_th'])}</td>"
                       f"<td>{_e(s['dialogue_th']) or '—'}{' 🔊 อัดเสียง' if s['audio'] == 'sync' else ''}</td>"
                       f"<td>≥ {s['min_seconds']:.0f} วิ</td></tr>")
        out.append("</table><h3>ลำดับการตัดต่อ (อัตโนมัติ)</h3><table><tr><th>#</th><th>ช็อต</th><th>วินาที</th>"
                   "<th>เสียงพูด</th><th>กราฟิก</th></tr>")
        for i, b in enumerate(v["timeline"], 1):
            ovs = ", ".join(f"{o['type']}" + (f" “{_e(o['text'])}”" if o["text"] else "") for o in b["overlays"])
            out.append(f"<tr><td>{i}</td><td>{_e(b['shot_id'])}</td><td>{b['duration']:.1f}</td>"
                       f"<td>{_e(b['vo_th'])}</td><td>{ovs}</td></tr>")
        out.append("</table>")
        out.append(f"<p><b>แคปชันโพสต์:</b> {_e(v['post_caption_th'])}<br>{_e(' '.join(v['hashtags']))}</p>")
    out.append("</body></html>")
    return "\n".join(out)


def scripts_text(plan: dict) -> str:
    lines = []
    for v in plan["videos"]:
        lines += [f"===== {v['id']} (rank {v['rank']}, score {v['score']['total']:.0f}) — {v['title_th']} =====",
                  f"Format: {v['format']} | Hook: {v['hook_type']} | Mode: {v['audio_mode']}",
                  f"Angle: {v['angle_en']}", "", v["full_script_th"], "",
                  "Caption: " + v["post_caption_th"], " ".join(v["hashtags"]), ""]
    return "\n".join(lines)


def write_all(d: Path, plan: dict, meta: dict) -> None:
    (d / "filming_pack.html").write_text(filming_pack_html(plan, meta), "utf-8")
    (d / "scripts.txt").write_text(scripts_text(plan), "utf-8")
