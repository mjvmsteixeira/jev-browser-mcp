"""Guarded jev-ultrafast loop: domain allowlist, step/time budget, irreversible-action stop."""

import os
import re
import time
from urllib.parse import urlsplit

from jev_ultrafast.browser import StalePage

IRREVERSIBLE = re.compile(
    r"\b(buy|purchase|pay|checkout|check out|place order|order now|confirm order|book now|reserve|subscribe|"
    r"delete|remove|unsubscribe|send|post|publish|transfer|sign up|register|"
    r"comprar|compra|pagar|pagamento|finalizar|encomendar|reservar|subscrever|apagar|eliminar|remover|"
    r"enviar|publicar|transferir|registar|inscrever)\b",
    re.IGNORECASE,
)
PRICE_PER_MTOK = float(os.environ.get("JEV_PRICE_PER_MTOK", "0.042"))  # docs.typesafe.ai/models
BLOCKED_RETRIES = 2
INVALID_RETRIES = 2
BLOCKED_WAIT_S = 1.5
STALL_REPEATS = 4
WAIT_STALL_MS = 20000
PAGE_TEXT = "document.body ? document.body.innerText.slice(0, {limit}) : ''"


def normalize_domains(domains):
    cleaned = {d.strip().lower().lstrip(".").removeprefix("www.") for d in domains if d and d.strip()}
    if not cleaned:
        raise ValueError("allowed_domains must list at least one domain")
    return cleaned


def host_allowed(url, domains):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        return parts.scheme == "about"
    host = (parts.hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def guard(action, page, domains, allow_irreversible):
    """Return a stop reason for an action that must not execute, else None."""
    if action["kind"] not in {"click", "select"}:
        return None
    href = (page.get("guards", {}).get(str(action.get("node"))) or [None] * 13)[12]
    if href:
        absolute = re.match(r"[a-z][a-z0-9+.-]*:", href, re.I)
        target = "https:" + href if href.startswith("//") else href if absolute else None
        local = ("javascript:", "mailto:", "tel:")
        if target and not target.lower().startswith(local) and not host_allowed(target, domains):
            return ("domain_blocked", f"'{action['label']}' leads outside allowed_domains: {target}")
    if not allow_irreversible and action.get("role") in {"button", "link", "menuitem"} and IRREVERSIBLE.search(
        action["label"]
    ):
        return ("needs_confirmation", f"'{action['label']}' looks irreversible; not clicked")
    return None


def stalled(history):
    """Loops jev misses (it only stops on unchanged pages, and never on WAIT).

    WAIT: waiting without interruption for WAIT_STALL_MS. Scroll: never (long pages are legitimate).
    Otherwise: the same operation on the same element STALL_REPEATS times, whatever option is selected.
    """
    if not history or history[-1]["kind"] == "scroll":
        return False
    if history[-1]["kind"] == "wait":
        waits = []
        for h in reversed(history):
            if h["kind"] != "wait":
                break
            waits.append(h)
        return waits[0]["executed_ms"] - waits[-1]["executed_ms"] >= WAIT_STALL_MS
    recent = {(h["kind"], h["action"].split(" → ")[0]) for h in history[-STALL_REPEATS:]}
    return len(history) >= STALL_REPEATS and len(recent) == 1


def spend(decisions, verification):
    """Input tokens only: Jev bills input and gives output away."""
    tokens = sum((d.get("usage") or {}).get("input_tokens") or 0 for d in decisions)
    tokens += ((verification or {}).get("usage") or {}).get("input_tokens") or 0
    return {"input_tokens": tokens, "usd": round(tokens * PRICE_PER_MTOK / 1_000_000, 6)}


def step_summary(h):
    return {k: h.get(k) for k in ("step", "operation", "action", "kind", "text", "url", "page_changed")}


def run_task(
    agent_factory,
    start_url,
    objective,
    allowed_domains,
    *,
    max_steps=25,
    timeout_s=90,
    allow_irreversible=False,
    max_text_chars=20000,
    keep_open=False,
    verifier=None,
):
    domains = normalize_domains(allowed_domains)
    if not host_allowed(start_url, domains):
        return {"status": "domain_blocked", "reason": f"start_url is outside allowed_domains: {start_url}"}
    started = time.monotonic()
    agent = agent_factory(start_url, objective)
    state = agent.state
    status, reason = None, None
    blocked_retries = 0
    invalid_retries = 0
    try:
        while True:
            if not host_allowed(state["page"]["url"], domains):
                status, reason = "domain_blocked", f"Navigated outside allowed_domains: {state['page']['url']}"
                break
            if state["status"] == "blocked" and blocked_retries < BLOCKED_RETRIES:
                # Jev gives up on content that is still arriving (measured: a 5s async load).
                # Give it another look only if the page actually changed while we waited.
                blocked_retries += 1
                time.sleep(BLOCKED_WAIT_S)
                before = state["page"]["fingerprint"]
                state["page"] = agent.browser.observe(screenshot=False)
                if state["page"]["fingerprint"] != before:
                    state["status"], state["decision"] = "ready", None
                    continue
            if state["status"] in {"done", "blocked"}:
                status = state["status"]
                reason = (
                    "Agent chose DONE; verify the outcome"
                    if status == "done"
                    else f"Agent could not progress (retried {blocked_retries}x while the page changed)"
                )
                break
            if time.monotonic() - started > timeout_s:
                status, reason = "timeout", f"Stopped after {timeout_s}s"
                break
            if stalled(state["history"]):
                last = state["history"][-1]
                status = "stalled"
                reason = f"Looping on {last['kind']} '{last['action'][:60]}'; the goal may already be met"
                break
            if len(state["history"]) >= max_steps:
                status, reason = "step_budget", f"Stopped after {max_steps} actions"
                break
            try:
                agent.command("predict")
                page, decision = state["page"], state["decision"]
                action = next((a for a in page["actions"] if a["id"] == decision["choice"]), None)
                stop = action and guard(action, page, domains, allow_irreversible)
                if stop:
                    state["decision"] = None
                    status, reason = stop
                    break
                agent.command("act", {"fingerprint": page["fingerprint"]})
            except StalePage:
                state["decision"] = None
                state["status"] = "ready"
                state["page"] = agent.browser.observe(screenshot=False)
            except (ValueError, RuntimeError) as error:
                # A malformed answer is transient; one of them should not end the whole task.
                if "Invalid TypeSafe response" in str(error) and invalid_retries < INVALID_RETRIES:
                    invalid_retries += 1
                    state["decision"] = None
                    continue
                status, reason = "error", str(error)
                break
        page = state["page"]
        try:
            text = agent.browser.evaluate(PAGE_TEXT.format(limit=int(max_text_chars)))
        except Exception:
            text = page.get("text", "")
        verification = verifier(objective, page["url"], page["title"], text) if verifier else None
        if verification and verification.get("passed") is False and status == "done":
            status = "unverified"
            reason = f"Agent chose DONE but the check failed on: {', '.join(verification['failed'])}"
        elif verification and verification.get("passed") and status != "done":
            # Measured: the agent gave up on a page that already satisfied the goal.
            reason = f"{reason}; the check says the goal appears satisfied"
        return {
            "status": status,
            "reason": reason,
            "verification": verification,
            "final_url": page["url"],
            "title": page["title"],
            "page_text_untrusted": text,
            "steps": [step_summary(h) for h in state["history"]],
            "model_calls": len(state["decisions"]),
            "cost": spend(state["decisions"], verification),
            "text_calls": len(state["text_calls"]),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    finally:
        if not keep_open:
            agent.close()
