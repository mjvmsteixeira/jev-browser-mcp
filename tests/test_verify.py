"""Offline contracts for the DONE re-check. No API calls."""

import os

import httpx
import pytest

from jev_browser_mcp import runner
from jev_browser_mcp import verify as verify_module
from jev_browser_mcp.verify import QUESTIONS, verify


class Client:
    def __init__(self, payload=None, status=200, error=None):
        self.payload, self.status, self.error = payload, status, error
        self.sent = {}

    def post(self, url, json, headers, timeout):
        if self.error:
            raise self.error
        self.sent.update(json)
        response = httpx.Response(self.status, json=self.payload or {})
        return response


def answers(**values):
    return {"answers": {name: {"type": "noul", "noul": values.get(name, 1.0)} for name in QUESTIONS}}


def test_no_key_means_no_verification(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert verify("goal", "u", "t", "text") is None
    monkeypatch.setenv("TYPESAFE_API_KEY", "local")
    assert verify("goal", "u", "t", "text") is None


def test_all_high_scores_pass(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    client = Client(answers())
    result = verify("find flights", "https://x.test/", "X", "page", client=client)
    assert result["passed"] and not result["failed"]
    assert client.sent["state"]["goal"] == "find flights"
    assert set(client.sent["questions"]) == set(QUESTIONS)


def test_one_low_score_fails_and_names_the_question(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    result = verify("goal", "u", "t", "text", client=Client(answers(all_requirements=0.2)))
    assert result["passed"] is False
    assert result["failed"] == ["all_requirements"]


@pytest.mark.parametrize(
    "client",
    [Client(status=500), Client({"answers": {}}), Client(error=httpx.ConnectError("down"))],
)
def test_failures_never_claim_a_verdict(client, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    result = verify("goal", "u", "t", "text", client=client)
    assert result["passed"] is None and result["error"]


def test_page_text_is_capped(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    client = Client(answers())
    verify("goal", "u", "t", "x" * 50000, client=client)
    assert len(client.sent["state"]["page_text"]) == verify_module.TEXT_LIMIT


def test_failed_check_turns_done_into_unverified(monkeypatch):
    from tests.test_runner import FakeAgent, page, run

    agent = FakeAgent(page(), [("DONE", None)])
    result = run(agent, verifier=lambda *a: {"passed": False, "failed": ["all_requirements"], "scores": {}})
    assert result["status"] == "unverified"
    assert "all_requirements" in result["reason"]
    assert runner.stalled([]) is False


def test_cost_counts_input_tokens_only():
    decisions = [{"usage": {"input_tokens": 1000, "output_tokens": 50}}, {"usage": {"input_tokens": 500}}, {}]
    cost = runner.spend(decisions, {"usage": {"input_tokens": 500}})
    assert cost["input_tokens"] == 2000
    assert cost["usd"] == round(2000 * runner.PRICE_PER_MTOK / 1_000_000, 6)


def test_backend_reads_the_key_from_vault_when_missing(monkeypatch, tmp_path):
    from jev_browser_mcp import server

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("JEV_DECISION_BACKEND", raising=False)
    monkeypatch.setattr(server, "VAULT_READ", str(tmp_path / "missing.sh"))
    assert server.backend() == "ollama"
    reader = tmp_path / "vault-read.sh"
    reader.write_text("#!/bin/sh\necho apikey_from_vault\n")
    reader.chmod(0o755)
    monkeypatch.setattr(server, "VAULT_READ", str(reader))
    assert server.backend() == "typesafe"
    assert os.environ["TYPESAFE_API_KEY"] == "apikey_from_vault"


def test_a_passing_check_flags_a_goal_reached_after_the_agent_gave_up(monkeypatch):
    from tests.test_runner import FakeAgent, page, run

    monkeypatch.setattr(runner.time, "sleep", lambda _s: None)
    agent = FakeAgent(page(), [("BLOCKED", None)])
    agent.browser.pages = [page(), page()]  # unchanged: the retry must not revive the run
    result = run(agent, verifier=lambda *a: {"passed": True, "failed": [], "scores": {"all_requirements": 0.9}})
    assert result["status"] == "blocked"
    assert "appears satisfied" in result["reason"]
