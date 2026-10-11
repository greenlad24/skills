"""Synthetic footage + a plan that exercises every overlay type (used by tests and the demo)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from studio.editor.media import ffmpeg_exe


def ov(type_, text="", at=0.0, dur=2.0, **kw):
    o = {"type": type_, "text": text, "sub_text": "", "items": [], "emoji": "", "at": at, "dur": dur,
         "position": "auto", "color": "auto", "target_x": 0.5, "target_y": 0.5}
    o.update(kw)
    return o


def beat(shot, dur, vo="", caps=None, overlays=None, sfx=None, effect="none", role="other", trim="start"):
    return {"shot_id": shot, "role": role, "duration": dur, "trim": trim, "speed": 1.0, "effect": effect,
            "vo_th": vo, "captions": caps or [], "overlays": overlays or [], "sfx": sfx or []}


def shot(id_, size="close_up", audio="mute", dialogue=""):
    return {"id": id_, "shot_size": size, "what_to_film_th": f"ถ่าย {id_} ให้เห็นสินค้าชัดๆ",
            "how_to_film_th": "ถือกล้องนิ่ง แสงจากหน้าต่าง", "dialogue_th": dialogue, "min_seconds": 4, "audio": audio}


def sample_plan() -> dict:
    v1 = {
        "id": "V1", "rank": 1, "title_th": "ราคาช็อก ที่นอน", "format": "price_shock", "hook_type": "price",
        "angle_en": "Mall price vs TikTok price", "why_it_works_en": "Price anchor.", "audio_mode": "voiceover",
        "target_length_sec": 14, "font": "kanit", "theme": "sale_red_yellow", "caption_style": "stroke_white",
        "music_mood": "upbeat", "progress_bar": True, "full_script_th": "ทำไมถูกจัง", "post_caption_th": "ที่นอนดี",
        "hashtags": ["ที่นอน"], "score": {"hook_strength": 9, "pain_or_desire": 8, "proof_demo": 7, "offer_clarity": 9,
                                          "trend_fit": 8, "filmability": 9, "compliance_safety": 10, "total": 0},
        "shots": [shot("V1-S01", "wide"), shot("V1-S02"), shot("V1-S03", "extreme_close_up"), shot("V1-S04", "medium")],
        "timeline": [
            beat("V1-S01", 2.4, "ทำไมถูกจัง ที่นอนห้าฟุต แค่สองพันกว่าบาท",
                 [{"text": "ทำไมถูกจัง", "highlight": ["ถูกจัง"]}, {"text": "ที่นอน 5 ฟุต แค่ 2,000", "highlight": ["2,000"]}],
                 [ov("hook_title", "ในห้างเป็นหมื่น แต่ในคลิปนี้…", 0, 2.4), ov("emoji_sticker", emoji="😱", at=0.6, dur=1.2)],
                 [{"type": "whoosh", "at": 0}], effect="punch_in", role="hook"),
            beat("V1-S02", 3.0, "นุ่มเด้ง ไม่ปวดหลัง", [{"text": "นุ่มเด้ง ไม่ปวดหลัง", "highlight": ["นุ่มเด้ง"]}],
                 [ov("checklist", items=["นุ่มเด้ง", "ไม่ปวดหลัง", "ส่งฟรี"], at=0.2, dur=2.8),
                  ov("arrow", at=0.5, dur=1.5, position="target", target_x=0.62, target_y=0.55)],
                 [{"type": "tick", "at": 0.2}], effect="flash", role="demo"),
            beat("V1-S03", 2.6, "ราคาเหลือแค่ 2,990", [],
                 [ov("keyword_pop", "คุ้มมาก!", 0, 2.6), ov("circle_highlight", at=0.2, dur=1.6, position="target", target_x=0.35, target_y=0.4)],
                 [{"type": "cash", "at": 0}], effect="punch_shake", role="price"),
            beat("V1-S04", 2.4, "", [], [ov("stars_rating", "4.9", 0, 2.4, sub_text="ขายแล้ว 10k+"), ov("discount_badge", "ลด 50%", 0.3, 2)],
                 [{"type": "sparkle", "at": 0}], effect="slow_zoom", role="proof"),
            beat("V1-S02", 3.0, "กดตะกร้าเหลืองได้เลย", [], [ov("cta_basket", "กดตะกร้าเลย", 0, 3, emoji="🛒")],
                 [{"type": "ding", "at": 0}], role="cta", trim="end"),
        ],
    }
    v2 = {
        **v1, "id": "V2", "rank": 2, "format": "reply_to_comment", "audio_mode": "talking", "theme": "beauty_pink",
        "font": "mitr", "caption_style": "box_black", "progress_bar": False,
        "shots": [shot("V2-S01", "selfie_talking", "sync", "ใช่ค่ะ นุ่มจริง"), shot("V2-S02"), shot("V2-S03", "product_photo")],
        "timeline": [
            beat("V2-S01", 3, "ใช่ค่ะ นุ่มจริง", [{"text": "ใช่ค่ะ นุ่มจริง", "highlight": ["นุ่มจริง"]}],
                 [ov("comment_reply", "นุ่มจริงไหมคะ?", 0, 3, sub_text="@mee"), ov("reaction_text", "จริงดิ?!", 1, 1.2, emoji="🤔")],
                 [{"type": "pop", "at": 0}], role="hook"),
            beat("V2-S02", 2.5, "", [], [ov("vs_split", "ก่อน", 0, 2.5, sub_text="หลัง"), ov("spec_card", "สเปก", 0.3, 2, items=["หนา: 10 นิ้ว", "ขนาด: 5 ฟุต"])]),
            beat("V2-S03", 2.5, "", [], [ov("number_badge", "1", 0, 2.5, sub_text="นุ่มเด้ง"), ov("trust_badges", items=["ของแท้", "ส่งฟรี"], at=0.2, dur=2),
                                          ov("lower_third", "Solomon Pyla Plus", 0.2, 2, sub_text="ที่นอนสปริง"), ov("urgency_banner", "โปรวันนี้วันเดียว", 0.5, 2),
                                          ov("speech_bubble", "นอนสบายมาก", 1, 1.4), ov("keyword_pop", "ปัง!!", 1.5, 1), ov("label", "หลัง", 0, 2.5),
                                          ov("before_after_labels", "ก่อน", 0, 2.5, position="top_right")], effect="shake"),
            beat("V2-S99", 2, "", [], [ov("cta_basket", "", 0, 2)]),
        ],
    }
    return {"research": {"product_name": "Solomon Pyla Plus"}, "videos": [v1, v2]}


def make_footage(d: Path) -> dict:
    """Create synthetic clips. V2-S01 has speech-like tone bursts with pauses (tests jump cuts)."""
    d.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_exe()
    specs = {
        "V1-S01.mp4": ("testsrc2=s=1280x720:r=30", 5), "v1_s2.mov": ("smptebars=s=720x1280:r=30", 6),
        "V1S03.mp4": ("rgbtestsrc=s=640x640:r=30", 4), "clip4.mp4": ("testsrc=s=1080x1920:r=30", 4),
    }
    for name, (src, dur) in specs.items():
        subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", f"{src}:d={dur}", "-pix_fmt", "yuv420p",
                        "-c:v", "libx264", "-preset", "ultrafast", str(d / name)], check=True)
    # talking clip: 0.6s silence, 1.2s tone, 0.9s silence, 1.0s tone, 0.8s silence
    aexpr = "if(between(t,0.6,1.8)+between(t,2.7,3.7),0.5*sin(2*PI*220*t),0)"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=4.5",
                    "-f", "lavfi", "-i", f"aevalsrc='{aexpr}':s=48000:d=4.5", "-shortest", "-pix_fmt", "yuv420p",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(d / "V2-S01.mp4")], check=True)
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=orange:s=900x900:d=1", "-frames:v", "1",
                    str(d / "product_1.jpg")], check=True)
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=330:d=20", str(d / "music_track.mp3")], check=True)
    return {"dir": d}


def make_unnamed_footage(d: Path) -> dict:
    """Camera-style names whose name order ≠ recording order, an extra take, a photo,
    a voice recording and a song. Returns the expected shot → file mapping."""
    from PIL import Image
    d.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_exe()
    talk = "if(between(t,0.3,1.6)+between(t,2.0,3.4),0.5*sin(2*PI*220*t),0)"
    clips = [  # name, minute recorded, talking?
        ("IMG_0105.MOV", 0, False), ("IMG_0103.MOV", 1, False), ("IMG_0110.MOV", 2, False),
        ("IMG_0111.MOV", 3, False), ("IMG_0120.MOV", 10, True), ("IMG_0121.MOV", 11, True),
        ("IMG_0122.MOV", 12, False),
    ]
    for name, minute, talking in clips:
        ct = f"2026-03-01T10:{minute:02d}:00Z"
        audio = (["-f", "lavfi", "-i", f"aevalsrc='{talk}':s=48000:d=4"] if talking
                 else ["-f", "lavfi", "-i", "anoisesrc=a=0.002:d=4"])
        subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=540x960:r=30:d=4", *audio,
                        "-shortest", "-metadata", f"creation_time={ct}", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                        "-preset", "ultrafast", "-c:a", "aac", str(d / name)], check=True)
    img = Image.new("RGB", (600, 600), (255, 140, 0))
    exif = Image.Exif()
    exif[306] = "2026:03:01 10:13:00"
    img.save(d / "IMG_0099.JPG", exif=exif)   # lowest name, but recorded last
    vo = "if(between(t,0.2,1.5)+between(t,2.0,3.3)+between(t,3.9,5.0),0.5*sin(2*PI*180*t),0)"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc='{vo}':s=48000:d=5.5",
                    str(d / "New Recording 3.m4a")], check=True)
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=330:d=20", "-af", "volume=0.5",
                    str(d / "song.mp3")], check=True)
    expected = {"V1-S01": "IMG_0105.MOV", "V1-S02": "IMG_0103.MOV", "V1-S03": "IMG_0110.MOV",
                "V1-S04": "IMG_0111.MOV", "V2-S01": "IMG_0121.MOV", "V2-S02": "IMG_0122.MOV",
                "V2-S03": "IMG_0099.JPG"}
    return {"shots": expected, "vo": {"V1": "New Recording 3.m4a"}, "music": ["song.mp3"],
            "unmatched": ["IMG_0120.MOV"]}
