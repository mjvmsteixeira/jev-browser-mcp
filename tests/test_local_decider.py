"""The local stand-in must satisfy jev_ultrafast's own response validation. No Ollama needed."""

import json

import pytest
from jev_ultrafast import model

from jev_browser_mcp import local_decider


def body():
    return {
        "model": "jev-latest",
        "state": {"page": {"url": "u", "title": "t", "text": "x"}, "elements": [], "recent_actions": []},
        "questions": {
            "operation": {
                "type": "choice",
                "criteria": {"CLICK": "c", "TYPE_TEXT": "t", "WAIT": "w", "DONE": "d", "BLOCKED": "b"},
                "instructions": {"goal": "g", "rules": "r"},
            },
            "click_target": {"type": "choice", "criteria": {"1": {}, "2": {}}, "instructions": {}},
            "type_text_target": {"type": "choice", "criteria": {"1": {}}, "instructions": {}},
        },
    }


class Reply:
    def __init__(self, content, status=200):
        self.status_code = status
        self.is_error = status >= 400
        self._content = content

    def json(self):
        return {"message": {"content": json.dumps(self._content)}, "prompt_eval_count": 10, "eval_count": 3}


def test_answers_pass_jev_validation(monkeypatch):
    sent = {}

    def post(url, json):
        sent.update(json)
        return Reply({"operation": "CLICK", "click_target": "2", "type_text_target": "1"})

    monkeypatch.setattr(local_decider.CLIENT, "post", post)
    result = local_decider.answer(body())
    assert set(sent["format"]["properties"]["click_target"]["enum"]) == {"1", "2"}
    ops = body()["questions"]["operation"]["criteria"]
    assert model.validate_choice(result["answers"]["operation"], ops)["choice"] == "CLICK"
    assert model.validate_choice(result["answers"]["click_target"], {"1", "2"})["choice"] == "2"


def test_invalid_operation_raises(monkeypatch):
    monkeypatch.setattr(local_decider.CLIENT, "post", lambda url, json: Reply({"operation": "HACK"}))
    with pytest.raises(ValueError, match="no action executed"):
        local_decider.answer(body())


def test_http_error_raises(monkeypatch):
    monkeypatch.setattr(local_decider.CLIENT, "post", lambda url, json: Reply({}, status=500))
    with pytest.raises(RuntimeError, match="HTTP 500"):
        local_decider.answer(body())


def test_install_routes_only_systemone(monkeypatch):
    calls = []
    monkeypatch.setattr(model, "post_json", lambda url, key, b: calls.append(url) or "remote")
    monkeypatch.setattr(local_decider, "answer", lambda b: "local")
    local_decider.install()
    assert model.post_json("https://api.typesafe.ai/v1/systemone", "k", {}) == "local"
    assert model.post_json("http://127.0.0.1:11434/v1/chat/completions", "k", {}) == "remote"
    assert calls == ["http://127.0.0.1:11434/v1/chat/completions"]
