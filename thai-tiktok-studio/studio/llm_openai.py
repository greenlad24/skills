"""ChatGPT provider via the OpenAI Responses API (plain HTTPS, no extra SDK)."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

import requests

from . import prompts
from .plan_schema import PLAN_SCHEMA

URL = "https://api.openai.com/v1/responses"


def _post(body: dict, key: str) -> dict:
    r = requests.post(URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=900)
    if r.status_code >= 400:
        try:
            err = r.json().get("error", {}).get("message", r.text)
        except ValueError:
            err = r.text
        raise RuntimeError(f"OpenAI API error {r.status_code}: {err[:400]}")
    return r.json()


def _text(resp: dict) -> str:
    out = []
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    out.append(c.get("text", ""))
    return "".join(out)


def _content(text: str, images: list) -> list:
    content = []
    for p in images[:6]:
        path = Path(p)
        mt = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        if path.exists() and mt.startswith("image/") and path.stat().st_size < 8_000_000:
            b64 = base64.b64encode(path.read_bytes()).decode()
            content.append({"type": "input_image", "image_url": f"data:{mt};base64,{b64}"})
    content.append({"type": "input_text", "text": text})
    return content


def research(gathered: dict, settings: dict, log=print) -> str:
    log("Researching on the web with ChatGPT…")
    resp = _post({
        "model": settings["openai_model"],
        "input": [{"role": "user", "content": _content(
            prompts.research_prompt(gathered),
            gathered.get("user_images", []) + gathered.get("product_images", [])[:2])}],
        "tools": [{"type": "web_search"}],
    }, settings["openai_api_key"])
    return _text(resp)


def make_plan(gathered: dict, dossier: str, settings: dict, log=print) -> dict:
    n = int(settings.get("videos_per_product", 5))
    log(f"Writing {n} scripts, shot lists and edit plans with ChatGPT…")
    try:
        return _plan(gathered, dossier, settings, n, structured=True)
    except RuntimeError as e:
        if "schema" not in str(e).lower():
            raise
        log("Structured output unavailable — retrying with JSON instructions…")
        return _plan(gathered, dossier, settings, n, structured=False)


def _plan(gathered, dossier, settings, n, structured: bool) -> dict:
    text = prompts.plan_prompt(gathered, dossier, n)
    if not structured:
        text += ("\n\nReply with ONE JSON object only (no markdown fences) matching this JSON Schema:\n"
                 + json.dumps(PLAN_SCHEMA, ensure_ascii=False))
    body = {
        "model": settings["openai_model"],
        "instructions": prompts.system_prompt(n),
        "input": [{"role": "user", "content": _content(text, gathered.get("user_images", []))}],
    }
    if structured:
        body["text"] = {"format": {"type": "json_schema", "name": "video_plan", "schema": PLAN_SCHEMA, "strict": True}}
    out = _text(_post(body, settings["openai_api_key"]))
    return json.loads(out[out.find("{"): out.rfind("}") + 1])
