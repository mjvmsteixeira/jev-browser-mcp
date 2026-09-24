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


def test_long_labels_are_capped(monkeypatch):
    from jev_ultrafast.browser import Browser

    from jev_browser_mcp import server

    long_label = "1900 1901 1902 " * 500
    actions = [
        {"label": long_label, "kind": "click", "node": 1},
        {"label": long_label + " → 1990", "kind": "select", "node": 2},
        {"label": "Search", "kind": "click", "node": 3},
    ]
    monkeypatch.setattr(Browser, "observe", lambda self, screenshot=True: {"actions": actions})
    server.patch_labels()
    labels = {a["kind"]: a["label"] for a in Browser.observe(object())["actions"] if a["node"] != 3}
    assert len(labels["click"]) == server.LABEL_MAX + 1
    # The option must survive: it is the only thing that tells 211 identical-looking entries apart.
    assert labels["select"].endswith(" → 1990")
    assert len(labels["select"]) == server.LABEL_MAX + 1 + len(" → 1990")


def test_select_options_are_capped_keeping_the_ones_named_in_the_goal():
    from jev_browser_mcp import server

    years = [{"kind": "select", "node": 7, "label": f"Year → {1900 + i}"} for i in range(120)]
    actions = [{"kind": "click", "node": 1, "label": "Submit"}, *years]
    kept = server.cap_options(actions, "Date of Birth 15 January 1990")
    labels = [a["label"] for a in kept if a["kind"] == "select"]
    assert len(labels) == server.SELECT_OPTIONS_MAX
    assert labels[0] == "Year → 1990"
    assert {a["label"] for a in kept if a["kind"] == "click"} == {"Submit"}
