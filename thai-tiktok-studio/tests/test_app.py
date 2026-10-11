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

    r = c.post(f"/api/projects/{pid}/render", json={"videos": ["V1"], "draft": True}).get_json()
    j = wait_job(c, r["job"]["id"])
    assert j["status"] == "done", j["log"]
    p = c.get(f"/api/projects/{pid}").get_json()
    assert p["renders"] and p["renders"][0]["name"].startswith("V1_draft")

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
