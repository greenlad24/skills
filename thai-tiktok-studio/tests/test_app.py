import io
import json
import time

import pytest
from fixtures import make_footage, sample_plan


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_STUDIO_HOME", str(tmp_path / "home"))
    import importlib

    import studio.config as config
    importlib.reload(config)
    import studio.projects as projects
    importlib.reload(projects)
    import studio.planner as planner
    importlib.reload(planner)
    import studio.editor.service as service
    importlib.reload(service)
    import studio.app as appmod
    importlib.reload(appmod)
    monkeypatch.setattr(planner.scrape, "gather", lambda text, imgs, d, log=print: {
        "input_text": text, "url": "", "name_hint": text, "page": {}, "search_results": [],
        "product_images": [], "user_images": imgs})
    config.save_settings({"provider": "manual"})
    appmod.app.testing = True
    return appmod.app.test_client(), tmp_path


def wait_job(c, jid, timeout=240):
    end = time.time() + timeout
    while time.time() < end:
        j = c.get(f"/api/jobs/{jid}").get_json()
        if j["status"] != "running":
            return j
        time.sleep(0.3)
    raise AssertionError("job timeout")


def test_manual_flow_upload_and_render(client):
    c, tmp = client
    assert c.get("/").status_code == 200
    r = c.post("/api/projects", data={"text": "ที่นอน Solomon", "notes": "",
                                      "images": (io.BytesIO(b"\x89PNG fake"), "shot.png")},
               content_type="multipart/form-data")
    body = r.get_json()
    pid = body["project"]["id"]
    assert wait_job(c, body["job"]["id"])["status"] == "done"
    p = c.get(f"/api/projects/{pid}").get_json()
    assert p["meta"]["status"] == "waiting_for_paste" and "OUTPUT FORMAT" in p["manual_prompt"]

    bad = c.post(f"/api/projects/{pid}/paste", json={"text": "not json"})
    assert bad.status_code == 400
    ok = c.post(f"/api/projects/{pid}/paste", json={"text": "```json\n" + json.dumps(sample_plan(), ensure_ascii=False) + "\n```"})
    assert ok.status_code == 200
    p = c.get(f"/api/projects/{pid}").get_json()
    assert p["meta"]["status"] == "planned" and len(p["plan"]["videos"]) == 2
    assert c.get(f"/files/{pid}/filming_pack.html").status_code == 200
    assert c.get(f"/files/{pid}/../../settings.json").status_code == 404

    foot = tmp / "src"
    make_footage(foot)
    files = [(open(f, "rb"), f.name) for f in sorted(foot.iterdir())]
    up = c.post(f"/api/projects/{pid}/upload", data={"files": files}, content_type="multipart/form-data").get_json()
    assert up["assign"]["shots"]["V1-S01"] == "V1-S01.mp4"

    nar = tmp / "nar"
    nar.mkdir()
    import subprocess
    from studio.editor.media import ffmpeg_exe
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=4",
                    "-f", "lavfi", "-i", "aevalsrc='if(between(t,0.3,1.5)+between(t,2,3.5),0.4*sin(2*PI*190*t),0)':s=48000:d=4",
                    "-shortest", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    str(nar / "narration.mov")], check=True)
    up = c.post(f"/api/projects/{pid}/upload", data={"kind": "narration", "files": [(open(nar / "narration.mov", "rb"), "narration.mov")]},
                content_type="multipart/form-data").get_json()
    assert up["assign"]["narration"] == {"V1": "narration.mov"}

    r = c.post(f"/api/projects/{pid}/render", json={"videos": ["V1"], "draft": True, "versions": 2}).get_json()
    j = wait_job(c, r["job"]["id"])
    assert j["status"] == "done", j["log"]
    assert any("continuous take" in line for line in j["log"])
    p = c.get(f"/api/projects/{pid}").get_json()
    names = sorted(x["name"] for x in p["renders"])
    assert len(names) == 2 and names[0].startswith("V1_bouncy_draft") and names[1].startswith("V1_punchy_draft")

    # review step: prepare all edits with previews → edit a sticker → preview → final render
    r = c.post(f"/api/projects/{pid}/prepare", json={"videos": ["V1"], "versions": 1}).get_json()
    j = wait_job(c, r["job"]["id"])
    assert j["status"] == "done", j["log"]
    edits = c.get(f"/api/projects/{pid}/edits").get_json()["edits"]
    assert len(edits) == 1 and edits[0]["preview"] and edits[0]["stickers"]
    e = edits[0]
    assert c.get(f"/files/{pid}/{e['preview']}").status_code == 200
    st = e["stickers"]
    upd = c.post(f"/api/projects/{pid}/edits/{e['key']}", json={"stickers": [
        {"i": st[0]["i"], "text": "ข้อความใหม่ 990 บาท"}, {"i": st[1]["i"], "hidden": True}]}).get_json()["edit"]
    assert upd["stickers"][0]["text"] == "ข้อความใหม่" and upd["stickers"][1]["hidden"] and upd["preview_stale"]
    assert c.post(f"/api/projects/{pid}/edits/../x", json={}).status_code in (400, 404)
    mv = c.post(f"/api/projects/{pid}/edits/{e['key']}", json={"stickers": [
        {"i": st[0]["i"], "x": 0.25, "y": 0.8, "tilt": 0}]}).get_json()["edit"]["stickers"][0]
    assert (mv["x"], mv["y"], mv["tilt"], mv["moved"]) == (0.25, 0.8, 0, True)
    back = c.post(f"/api/projects/{pid}/edits/{e['key']}", json={"stickers": [
        {"i": st[0]["i"], "x": None, "y": None, "tilt": None}]}).get_json()["edit"]["stickers"][0]
    assert not back["moved"]
    c.post(f"/api/projects/{pid}/edits/{e['key']}", json={"stickers": [{"i": st[0]["i"], "x": 0.25, "y": 0.8, "tilt": 0}]})
    rot = c.post(f"/api/projects/{pid}/edits/{e['key']}", json={"stickers": [{"i": st[2]["i"], "tilt": 170}]}).get_json()
    assert rot["edit"]["stickers"][2]["tilt"] == 170                 # full rotation allowed
    clips = c.get(f"/api/projects/{pid}/clips").get_json()["clips"]
    assert clips and all(x["rotate"] == 0 for x in clips)
    turned = c.post(f"/api/projects/{pid}/clips/turn", json={"name": clips[0]["name"], "degrees": 90}).get_json()
    assert turned["rotate"] == 90 and turned["manual"]
    assert c.get(f"/api/projects/{pid}/clips/thumb?name={clips[0]['name']}").status_code == 200
    assert c.get(f"/api/projects/{pid}/edits").get_json()["edits"][0]["preview_stale"]
    c.post(f"/api/projects/{pid}/clips/turn", json={"name": clips[0]["name"], "degrees": 270})   # back upright
    fr = c.get(f"/api/projects/{pid}/edits/{e['key']}/frame?t=1.0")
    assert fr.status_code == 200 and fr.mimetype == "image/jpeg"
    j = wait_job(c, c.post(f"/api/projects/{pid}/edits/{e['key']}/preview").get_json()["job"]["id"])
    assert j["status"] == "done", j["log"]
    assert not c.get(f"/api/projects/{pid}/edits").get_json()["edits"][0]["preview_stale"]
    j = wait_job(c, c.post(f"/api/projects/{pid}/render-final", json={"keys": [e["key"]]}).get_json()["job"]["id"])
    assert j["status"] == "done", j["log"]
    p = c.get(f"/api/projects/{pid}").get_json()
    assert len(p["renders"]) == 3 and p["edits"][0]["rendered"]
    # delete finished videos (one or a selection)
    gone = c.post(f"/api/projects/{pid}/renders/delete", json={"names": names + ["../../settings.json"]}).get_json()
    assert sorted(gone["deleted"]) == names
    assert len(c.get(f"/api/projects/{pid}").get_json()["renders"]) == 1

    plan = p["plan"]
    plan["videos"][0]["timeline"][0]["vo_th"] = "แก้บทแล้ว"
    assert c.post(f"/api/projects/{pid}/plan", json={"plan": plan}).status_code == 200
    assert c.get(f"/api/projects/{pid}").get_json()["plan"]["videos"][0]["timeline"][0]["vo_th"] == "แก้บทแล้ว"


def test_settings_masks_keys(client):
    c, _ = client
    s = c.post("/api/settings", json={"anthropic_api_key": "sk-ant-secret-1234"}).get_json()
    assert s["anthropic_api_key"].endswith("1234") and "secret" not in s["anthropic_api_key"]
    s2 = c.post("/api/settings", json={"anthropic_api_key": s["anthropic_api_key"]}).get_json()
    assert s2["anthropic_api_key"] == s["anthropic_api_key"]  # masked value doesn't overwrite


def test_password_login(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_STUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TTS_STUDIO_PASSWORD", "s3cret")
    import importlib

    import studio.config as config
    importlib.reload(config)
    import studio.app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    assert c.get("/").status_code == 302 and c.get("/api/projects").status_code == 401
    assert c.get("/static/style.css").status_code == 200          # login page can load its styles
    assert "รหัสผ่านไม่ถูกต้อง" in c.post("/login", data={"password": "nope"}).get_data(as_text=True)
    assert c.post("/login", data={"password": "s3cret"}).status_code == 302
    assert c.get("/api/projects").status_code == 200
    monkeypatch.delenv("TTS_STUDIO_PASSWORD")
    importlib.reload(appmod)


def test_missing_project_is_404(client):
    c, _ = client
    assert c.get("/api/projects/20990101-000000-nope").status_code == 404
    r = c.post("/api/projects/20990101-000000-nope/upload", data={}, content_type="multipart/form-data")
    assert r.status_code == 404 and "error" in r.get_json()


def test_phone_upload_via_qr_link(client):
    c, tmp = client
    r = c.post("/api/projects", data={"text": "ที่นอน"}, content_type="multipart/form-data").get_json()
    pid = r["project"]["id"]
    wait_job(c, r["job"]["id"])
    link = c.post(f"/api/projects/{pid}/phone-link").get_json()
    assert link["qr"].startswith("data:image/png;base64,") and "/m/" in link["url"]
    path = "/m/" + link["url"].split("/m/")[1]
    phone = {"REMOTE_ADDR": "192.168.1.50"}                 # another device on the Wi-Fi
    assert c.get("/", environ_base=phone).status_code == 403            # main app stays private
    assert c.get(f"/api/projects/{pid}", environ_base=phone).status_code == 403
    page = c.get(path, environ_base=phone)
    assert page.status_code == 200 and "ส่งไฟล์ไปที่ Mac" in page.get_data(as_text=True)
    up = c.post(path + "/upload", environ_base=phone, content_type="multipart/form-data",
                data={"kind": "narration", "files": [(io.BytesIO(b"x" * 1000), "VID_20261011.mp4")]})
    assert up.status_code == 200 and up.get_json()["saved"] == ["VID_20261011.mp4"]
    p = c.get(f"/api/projects/{pid}").get_json()
    assert [f["name"] for f in p["narration"]] == ["VID_20261011.mp4"]
    assert c.get("/m/not-a-real-token", environ_base=phone).status_code == 404
    assert c.post("/m/not-a-real-token/upload", environ_base=phone).status_code == 404
