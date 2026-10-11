import json

import anthropic
import httpx2
from fixtures import sample_plan

from studio import llm_claude, llm_openai

SETTINGS = {"claude_model": "claude-opus-5-5", "openai_model": "gpt-5", "openai_api_key": "k",
            "anthropic_api_key": "k", "videos_per_product": 2}
G = {"input_text": "x", "user_images": [], "product_images": []}


def test_claude_falls_back_when_schema_rejected(monkeypatch):
    calls = []

    def fake(gathered, dossier, settings, n, log, structured):
        calls.append(structured)
        if structured:
            req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.BadRequestError("output_config.format: schema too complex",
                                            response=httpx2.Response(400, request=req), body=None)
        return sample_plan()
    monkeypatch.setattr(llm_claude, "_make_plan", fake)
    assert llm_claude.make_plan(G, "", SETTINGS, log=lambda m: None)["videos"]
    assert calls == [True, False]


def test_openai_structured_then_fallback(monkeypatch):
    bodies = []

    class Resp:
        def __init__(self, status, payload):
            self.status_code, self._p, self.text = status, payload, json.dumps(payload)

        def json(self):
            return self._p

    def post(url, json=None, headers=None, timeout=None):
        bodies.append(json)
        if "text" in json:
            return Resp(400, {"error": {"message": "Invalid schema for response_format"}})
        out = "Here:\n" + __import__("json").dumps(sample_plan(), ensure_ascii=False)
        return Resp(200, {"output": [{"type": "message", "content": [{"type": "output_text", "text": out}]}]})
    monkeypatch.setattr(llm_openai.requests, "post", post)
    plan = llm_openai.make_plan(G, "", SETTINGS, log=lambda m: None)
    assert plan["videos"][0]["id"] == "V1"
    assert "text" in bodies[0] and "text" not in bodies[1]
