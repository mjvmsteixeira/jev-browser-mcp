"""The tool itself and the MCP protocol layer: offline, with a stubbed browser and agent."""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from jev_browser_mcp import server

TOOL = server.browse_interactive.fn if hasattr(server.browse_interactive, "fn") else server.browse_interactive


@pytest.fixture
def stub(monkeypatch):
    """No Chrome, no models: only the wiring under test."""
    calls = {}

    def run_task(*_args, **kwargs):
        calls["kwargs"] = kwargs
        return {"status": "done"}

    monkeypatch.setattr(server, "ensure_chrome", lambda: calls.__setitem__("chrome", True))
    monkeypatch.setattr(server, "prepare_models", lambda: calls.__setitem__("models", True))
    monkeypatch.setattr(server, "run_task", run_task)
    return calls


def test_typesafe_backend_wires_the_verifier(stub, monkeypatch):
    monkeypatch.setenv("JEV_DECISION_BACKEND", "typesafe")
    result = TOOL("https://x.test/", "goal", ["x.test"])
    assert result["decision_backend"] == "typesafe"
    assert stub["kwargs"]["verifier"] is server.verify
    assert stub["chrome"] and stub["models"]


def test_local_backend_installs_the_decider_and_skips_verification(stub, monkeypatch):
    monkeypatch.setenv("JEV_DECISION_BACKEND", "ollama")
    installed = []
    monkeypatch.setattr(server.local_decider, "install", lambda: installed.append(True))
    result = TOOL("https://x.test/", "goal", ["x.test"])
    assert result["decision_backend"] == "ollama"
    assert stub["kwargs"]["verifier"] is None
    assert installed


def test_objective_reaches_the_observe_patch(stub, monkeypatch):
    monkeypatch.setenv("JEV_DECISION_BACKEND", "ollama")
    monkeypatch.setattr(server.local_decider, "install", lambda: None)
    TOOL("https://x.test/", "pick the year 1990", ["x.test"])
    assert server.OBJECTIVE == "pick the year 1990"


def test_a_second_run_is_refused_while_one_holds_the_lock(stub, monkeypatch):
    monkeypatch.setenv("JEV_DECISION_BACKEND", "typesafe")
    server.LOCK.acquire()
    try:
        result = TOOL("https://x.test/", "goal", ["x.test"])
    finally:
        server.LOCK.release()
    assert result["status"] == "error" and "in progress" in result["reason"]


def test_a_crash_becomes_a_status_and_releases_the_lock(stub, monkeypatch):
    monkeypatch.setenv("JEV_DECISION_BACKEND", "typesafe")
    monkeypatch.setattr(server, "ensure_chrome", lambda: (_ for _ in ()).throw(RuntimeError("no Chrome")))
    result = TOOL("https://x.test/", "goal", ["x.test"])
    assert result["status"] == "error" and "no Chrome" in result["reason"]
    assert server.LOCK.acquire(blocking=False)
    server.LOCK.release()


@pytest.mark.anyio
async def test_the_tool_is_reachable_over_the_mcp_protocol(stub, monkeypatch):
    monkeypatch.setenv("JEV_DECISION_BACKEND", "typesafe")
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as client:
        tools = (await client.list_tools()).tools
        assert [t.name for t in tools] == ["browse_interactive"]
        assert tools[0].inputSchema["required"] == ["start_url", "objective", "allowed_domains"]
        result = await client.call_tool(
            "browse_interactive",
            {"start_url": "https://x.test/", "objective": "goal", "allowed_domains": ["x.test"]},
        )
        assert '"status": "done"' in result.content[0].text


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_enter_is_offered_only_when_the_page_has_an_editable_field(monkeypatch):
    from jev_ultrafast.browser import Browser

    pages = iter(
        [
            {"actions": [{"kind": "fill", "node": 1, "label": "Search"}]},
            {"actions": [{"kind": "click", "node": 1, "label": "Link"}]},
        ]
    )
    monkeypatch.setattr(Browser, "observe", lambda self, screenshot=True: next(pages))
    server.patch_labels()
    with_field = [a["id"] for a in Browser.observe(object())["actions"] if a.get("id")]
    without_field = [a["id"] for a in Browser.observe(object())["actions"] if a.get("id")]
    assert with_field == ["press_enter"]
    assert without_field == []


def test_enter_dispatches_a_key_pair_and_other_actions_pass_through(monkeypatch):
    from jev_ultrafast.browser import Browser

    sent, delegated = [], []
    monkeypatch.setattr(Browser, "act", lambda self, action, page, text=None: delegated.append(action["kind"]))
    monkeypatch.setattr(Browser, "fresh", lambda self, page, action=None: True)
    monkeypatch.setattr(Browser, "call", lambda self, method, **params: sent.append((method, params)))
    server.patch_enter()

    browser = Browser.__new__(Browser)
    result = Browser.act(browser, dict(server.ENTER), {"marker": 1})
    assert result == {"executed": "press_enter"}
    assert [event["type"] for _, event in sent] == ["keyDown", "keyUp"]
    assert {event["key"] for _, event in sent} == {"Enter"}
    assert browser.after_input is None

    Browser.act(browser, {"kind": "click", "node": 1, "label": "Go"}, {"marker": 1})
    assert delegated == ["click"]


def test_enter_refuses_a_stale_page(monkeypatch):
    from jev_ultrafast.browser import Browser, StalePage

    monkeypatch.setattr(Browser, "act", lambda *a, **kw: None)
    monkeypatch.setattr(Browser, "fresh", lambda self, page, action=None: False)
    server.patch_enter()
    with pytest.raises(StalePage):
        Browser.act(Browser.__new__(Browser), dict(server.ENTER), {"marker": 1})
