"""i18n checks: both dictionaries match, every key the UI uses exists, server pages translate."""

import json
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "studio" / "web"
TH = json.loads((WEB / "lang" / "th.json").read_text("utf-8"))
EN = json.loads((WEB / "lang" / "en.json").read_text("utf-8"))
JS = (WEB / "app.js").read_text("utf-8")
HTML = (WEB / "index.html").read_text("utf-8")
NAMESPACES = sorted({k.split(".")[0] for k in TH})


def test_same_keys_in_both_languages():
    assert set(TH) == set(EN), {"only_th": sorted(set(TH) - set(EN)), "only_en": sorted(set(EN) - set(TH))}


def test_no_empty_strings_and_placeholders_match():
    for k in TH:
        assert TH[k].strip() and EN[k].strip(), k
        assert set(re.findall(r"\{(\w+)\}", TH[k])) == set(re.findall(r"\{(\w+)\}", EN[k])), k


def test_thai_dictionary_is_thai():
    thai = [k for k, v in TH.items() if re.search(r"[฀-๿]", v)]
    assert len(thai) > 0.8 * len(TH)


def _used_keys(src: str):
    """Every quoted string that looks like a key ("ns.something") — also catches keys in ternaries."""
    ns = "|".join(map(re.escape, NAMESPACES))
    return set(re.findall(r"""["'`]((?:%s)\.[A-Za-z0-9_.]*)["'`]""" % ns, src))


@pytest.mark.parametrize("src", [JS, HTML], ids=["app.js", "index.html"])
def test_every_used_key_exists(src):
    missing = []
    for k in _used_keys(src):
        if k.endswith(".") or k.endswith("_"):        # dynamic: t("status." + x) → some key must start with it
            if not any(x.startswith(k) for x in TH):
                missing.append(k)
        elif k not in TH:
            missing.append(k)
    assert not missing, missing


def test_direct_t_calls_use_literal_known_keys():
    calls = re.findall(r"""\btt?\(\s*["']([^"']+)["']\s*[,)]""", JS)   # t("a.b") / t("a.b", vars)
    assert calls
    assert [c for c in calls if c not in TH] == []


def test_no_hardcoded_thai_in_app_js():
    """User-facing text lives in the dictionaries, not in the code."""
    # Language names stay in their own language (ไทย / English); the baht sign is allowed.
    assert not re.search("[\u0e00-\u0e3e\u0e40-\u0e7f]", JS.replace(">ไทย<", ""))


def test_login_and_phone_pages_follow_language(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_STUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TTS_STUDIO_PASSWORD", "pw")
    import importlib

    import studio.config as config
    importlib.reload(config)
    import studio.app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    assert TH["login.button"] in c.get("/login").get_data(as_text=True)
    assert EN["login.button"] in c.get("/login?lang=en").get_data(as_text=True)
    c.set_cookie("tts_lang", "en")
    assert EN["login.wrong"] in c.post("/login", data={"password": "x"}).get_data(as_text=True)
    from studio import phone
    assert EN["phonepage.clips"] in phone.page("x", "en") and TH["phonepage.clips"] in phone.page("x", "th")
    assert TH["phonepage.expired"] in phone.expired_page("th")
    monkeypatch.delenv("TTS_STUDIO_PASSWORD")
    importlib.reload(appmod)
