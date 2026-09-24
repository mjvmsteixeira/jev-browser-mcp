"""Offline contracts for the guarded loop. No browser, no paid APIs."""

import pytest
from jev_ultrafast.browser import StalePage

from jev_browser_mcp import runner


def page(url="https://shop.test/", actions=None, guards=None):
    return {
        "url": url,
        "title": "Shop",
        "text": "visible",
        "fingerprint": url,
        "actions": actions or [],
        "guards": guards or {},
    }


class FakeBrowser:
    def __init__(self, pages):
        self.pages = pages

    def observe(self, screenshot=False):
        return self.pages.pop(0)

    def evaluate(self, _expression):
        return "full page text"


class FakeAgent:
    """Replays scripted decisions; `act` moves to the next scripted page."""

    def __init__(self, first, script, stale_once=False):
        self.state = dict(page=first, decision=None, history=[], status="ready", decisions=[], text_calls=[])
        self.script = list(script)
        self.browser = FakeBrowser([])
        self.stale_once = stale_once
        self.closed = False
        self.acted = []

    def command(self, name, body=None):
        if name == "predict":
            if self.stale_once:
                self.stale_once = False
                self.browser.pages.append(self.state["page"])
                raise StalePage("changed")
            choice, _next_page = self.script[0]
            self.state["decision"] = {"choice": choice}
            self.state["decisions"].append({"choice": choice})
        elif name == "act":
            choice, next_page = self.script.pop(0)
            self.acted.append(choice)
            self.state["decision"] = None
            if choice in {"DONE", "BLOCKED"}:
                self.state["status"] = choice.lower()
                return
            step = len(self.state["history"]) + 1
            self.state["history"].append({"step": step, "action": choice, "kind": "click", "url": "u"})
            self.state["page"] = next_page

    def close(self):
        self.closed = True


def run(agent, **kwargs):
    kwargs.setdefault("allowed_domains", ["shop.test"])
    return runner.run_task(lambda _u, _g: agent, "https://shop.test/", "goal", **kwargs)


def button(label, node=1, role="button"):
    return {"id": f"e{node}", "kind": "click", "label": label, "role": role, "node": node}


def test_domains_match_subdomains_not_suffix_tricks():
    domains = runner.normalize_domains(["www.Shop.test", " "])
    assert runner.host_allowed("https://a.shop.test/x", domains)
    assert runner.host_allowed("https://shop.test", domains)
    assert not runner.host_allowed("https://evilshop.test", domains)
    assert not runner.host_allowed("file:///etc/passwd", domains)
    with pytest.raises(ValueError):
        runner.normalize_domains([" "])


def test_start_url_outside_allowlist_never_opens_a_browser():
    def factory(_u, _g):
        raise AssertionError("browser opened")

    result = runner.run_task(factory, "https://other.test/", "goal", ["shop.test"])
    assert result["status"] == "domain_blocked"


def test_done_returns_full_text_and_closes_tab():
    agent = FakeAgent(page(), [("e1", page()), ("DONE", None)])
    agent.state["page"]["actions"] = [button("Search")]
    result = run(agent)
    assert result["status"] == "done"
    assert result["page_text_untrusted"] == "full page text"
    assert [s["action"] for s in result["steps"]] == ["e1"]
    assert agent.closed


def test_irreversible_click_stops_before_execution():
    agent = FakeAgent(page(actions=[button("Place order")]), [("e1", page())])
    result = run(agent)
    assert result["status"] == "needs_confirmation"
    assert agent.acted == []


def test_irreversible_click_allowed_when_approved():
    agent = FakeAgent(page(actions=[button("Comprar agora")]), [("e1", page()), ("DONE", None)])
    assert run(agent, allow_irreversible=True)["status"] == "done"
    assert agent.acted == ["e1", "DONE"]


def test_offsite_link_is_not_clicked():
    guards = {"1": [None] * 12 + ["https://evil.test/login"]}
    agent = FakeAgent(page(actions=[button("Login", role="link")], guards=guards), [("e1", page())])
    result = run(agent)
    assert result["status"] == "domain_blocked"
    assert agent.acted == []


@pytest.mark.parametrize("href", ["/cart", "#top", "javascript:void(0)", "https://cdn.shop.test/a"])
def test_onsite_links_pass(href):
    guards = {"1": [None] * 12 + [href]}
    assert runner.guard(button("Open", role="link"), page(guards=guards), {"shop.test"}, False) is None


def test_protocol_relative_offsite_link_blocked():
    guards = {"1": [None] * 12 + ["//evil.test/x"]}
    assert runner.guard(button("Open", role="link"), page(guards=guards), {"shop.test"}, False)[0] == "domain_blocked"


def test_redirect_offsite_stops_after_the_step():
    agent = FakeAgent(page(actions=[button("Next")]), [("e1", page("https://evil.test/"))])
    result = run(agent)
    assert result["status"] == "domain_blocked"
    assert result["final_url"] == "https://evil.test/"


def test_step_budget():
    script = [(f"e{i}", page(actions=[button("Next", node=i + 1)])) for i in range(1, 6)]
    agent = FakeAgent(page(actions=[button("Next", node=1)]), script)
    result = run(agent, max_steps=3)
    assert result["status"] == "step_budget"
    assert len(result["steps"]) == 3


def test_timeout(monkeypatch):
    clock = iter([0, 0, 100, 100, 100])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(clock))
    agent = FakeAgent(page(actions=[button("Next")]), [("e1", page(actions=[button("Next")]))] * 3)
    assert run(agent, timeout_s=10)["status"] == "timeout"


def test_stale_page_reobserves_and_continues():
    agent = FakeAgent(page(actions=[button("Next")]), [("e1", page()), ("DONE", None)], stale_once=True)
    assert run(agent)["status"] == "done"


def test_model_errors_become_status_and_close_tab():
    agent = FakeAgent(page(), [])

    def boom(name, body=None):
        raise RuntimeError("Model provider returned HTTP 401; no action executed.")

    agent.command = boom
    result = run(agent)
    assert result["status"] == "error"
    assert "401" in result["reason"]
    assert agent.closed


def test_repeated_identical_action_stalls():
    script = [("e1", page(actions=[button("Next")])) for _ in range(10)]
    agent = FakeAgent(page(actions=[button("Next")]), script)
    result = run(agent)
    assert result["status"] == "stalled"
    assert len(result["steps"]) == runner.STALL_REPEATS


def h(kind, action, ms=0):
    return {"kind": kind, "action": action, "executed_ms": ms}


def test_stall_rules():
    same_select = [h("select", f"Year → {1900 + i}") for i in range(4)]
    assert runner.stalled(same_select)
    assert not runner.stalled([h("click", f"Link {i}") for i in range(6)])
    assert not runner.stalled([h("scroll", "Scroll down") for _ in range(10)])
    short_waits = [h("click", "Start")] + [h("wait", "Wait", ms) for ms in range(1000, 8000, 1000)]
    assert not runner.stalled(short_waits)
    long_waits = [h("wait", "Wait", ms) for ms in range(0, 21000, 1000)]
    assert runner.stalled(long_waits)


def loading(agent, pages):
    """The agent gives up; the browser then reports a page that is still changing."""
    agent.browser.pages = pages
    return agent


def test_blocked_is_retried_while_the_page_keeps_changing(monkeypatch):
    monkeypatch.setattr(runner.time, "sleep", lambda _s: None)
    agent = FakeAgent(page(), [("BLOCKED", None), ("e1", page()), ("DONE", None)])
    agent.state["page"]["actions"] = [button("Start")]
    loading(agent, [page(url="https://shop.test/?loaded")])
    result = run(agent)
    assert result["status"] == "done"
    assert agent.acted == ["BLOCKED", "e1", "DONE"]


def test_blocked_stands_when_the_page_is_static(monkeypatch):
    monkeypatch.setattr(runner.time, "sleep", lambda _s: None)
    agent = FakeAgent(page(), [("BLOCKED", None)])
    loading(agent, [page(), page()])
    result = run(agent)
    assert result["status"] == "blocked"
    assert "retried" in result["reason"]


def test_a_malformed_model_answer_is_retried_not_fatal():
    agent = FakeAgent(page(actions=[button("Next")]), [("e1", page()), ("DONE", None)])
    original = agent.command
    calls = {"n": 0}

    def flaky(name, body=None):
        calls["n"] += 1
        if name == "predict" and calls["n"] == 1:
            raise ValueError("Invalid TypeSafe response; no action executed.")
        return original(name, body)

    agent.command = flaky
    assert run(agent)["status"] == "done"


def test_repeated_malformed_answers_still_stop():
    agent = FakeAgent(page(actions=[button("Next")]), [("e1", page())])
    agent.command = lambda name, body=None: (_ for _ in ()).throw(
        ValueError("Invalid TypeSafe response; no action executed.")
    )
    result = run(agent)
    assert result["status"] == "error" and "Invalid TypeSafe" in result["reason"]
