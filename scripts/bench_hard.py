"""Hard live benchmark with independent outcome checks. Not run by pytest.

Uses whichever decision backend the server would pick (TypeSafe with a key, else local Ollama).
Usage: uv run python scripts/bench_hard.py [task-name ...]
"""

import functools
import http.server
import importlib.util
import json
import sys
import threading
import unicodedata
from pathlib import Path

from jev_browser_mcp import server
from jev_browser_mcp.runner import run_task
from jev_browser_mcp.server import backend, ensure_chrome, make_agent, prepare_models
from jev_browser_mcp.verify import verify

# find_spec does not execute jev_ultrafast, which must load after jev_browser_mcp sets the harness env.
FIXTURE_DIR = Path(importlib.util.find_spec("jev_ultrafast").submodule_search_locations[0]) / "static"
FIXTURE_PORT = 8767
BACKEND = "ollama"


def plain(text):
    """Accent-insensitive: the page says 'Zürich' where the goal said 'Zurich'."""
    stripped = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in stripped if not unicodedata.combining(c)).lower()


def has(*needles):
    return lambda r: all(plain(n) in plain(r.get("page_text_untrusted")) for n in needles)


def url_has(*needles):
    return lambda r: all(n.lower() in (r.get("final_url") or "").lower() for n in needles)


def both(*checks):
    return lambda r: all(c(r) for c in checks)


TASKS = [
    dict(
        name="fixture-hotel",
        kind="filters + search + open result (local, deterministic)",
        start_url=f"http://127.0.0.1:{FIXTURE_PORT}/fixture.html?scenario=travel",
        allowed_domains=["127.0.0.1"],
        objective="Use the destination search and filters to find Design stays in Lisbon with Free cancellation, "
        "then open Casa Flora.",
        check=both(url_has("#casa-flora"), has("Design · Free cancellation enabled · Destination Lisbon")),
    ),
    dict(
        name="dynamic-wait",
        kind="WAIT for async content",
        start_url="https://the-internet.herokuapp.com/dynamic_loading/2",
        allowed_domains=["the-internet.herokuapp.com"],
        objective="Click Start and wait until the loaded text is visible. Stop when 'Hello World!' is shown.",
        check=has("Hello World!"),
    ),
    dict(
        name="demoqa-form",
        kind="long form: autocomplete, react-select, date picker, radio, checkbox",
        start_url="https://demoqa.com/automation-practice-form",
        allowed_domains=["demoqa.com"],
        objective="Fill the practice form with test data: First Name 'Test', Last Name 'Agent', Email "
        "'test.agent@example.com', Gender 'Other', Mobile '9123456789', Date of Birth 15 January 1990 "
        "(use the date picker), Subjects 'Maths' (pick it from the autocomplete), Hobbies 'Reading', "
        "State 'NCR', City 'Delhi'. Then click Submit. Stop when the 'Thanks for submitting the form' dialog "
        "is visible.",
        check=has("Thanks for submitting the form", "Test Agent", "Maths", "Reading", "15 January,1990", "NCR Delhi"),
    ),
    dict(
        name="github-filters",
        kind="custom dropdown sort + language facet",
        start_url="https://github.com/search?q=browser%20agent&type=repositories",
        allowed_domains=["github.com"],
        objective="Narrow these repository results to the Rust language and sort them by Most stars. "
        "Stop when Rust repositories sorted by most stars are visible.",
        check=both(url_has("l=rust"), lambda r: "s=stars" in (r.get("final_url") or "") or has("Most stars")(r)),
    ),
    dict(
        name="google-flights",
        kind="consent banner + autocomplete + date picker (the jev showcase)",
        start_url="https://www.google.com/travel/flights?hl=en",
        allowed_domains=["google.com"],
        objective="Find one-way flights from Zurich to London on October 20, 2026, for one adult in economy. "
        "If a cookie consent screen appears, choose Reject all. Stop when matching flight options are visible.",
        check=has("Zurich", "London", "One way", "Oct 20"),
    ),
    dict(
        name="todomvc-enter",
        kind="LIMIT probe: needs the Enter key (no such operation)",
        start_url="https://todomvc.com/examples/react/dist/",
        allowed_domains=["todomvc.com"],
        objective="Add the todos 'milk' and 'eggs', mark 'eggs' as completed, then show only Active todos.",
        check=both(url_has("#/active"), has("milk")),
    ),
    dict(
        name="iframe-editor",
        kind="LIMIT probe: target inside an iframe (unsupported); should give up fast",
        start_url="https://the-internet.herokuapp.com/iframe",
        allowed_domains=["the-internet.herokuapp.com"],
        objective="Type 'hello from jev' into the rich text editor.",
        check=lambda r: r["status"] == "blocked",
    ),
]


def serve_fixture():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    handler = functools.partial(Quiet, directory=str(FIXTURE_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", FIXTURE_PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


def main():
    global BACKEND
    BACKEND = backend()
    wanted = set(sys.argv[1:])
    serve_fixture()
    ensure_chrome()
    prepare_models()
    rows = []
    for task in TASKS:
        if wanted and task["name"] not in wanted:
            continue
        print(f"\n=== {task['name']} ({task['kind']})", flush=True)
        server.OBJECTIVE = task["objective"]
        text_dump = Path(f"/private/tmp/claude-501/bench-{task['name']}.txt")
        try:
            result = run_task(
                make_agent,
                task["start_url"],
                task["objective"],
                task["allowed_domains"],
                max_steps=40,
                timeout_s=300,
                max_text_chars=50000,
                verifier=verify if BACKEND == "typesafe" else None,
            )
        except Exception as error:
            result = {"status": "error", "reason": f"{type(error).__name__}: {error}", "steps": []}
        text_dump.write_text(result.get("page_text_untrusted") or "")
        verified = bool(task["check"](result)) if result.get("final_url") or task["name"] == "iframe-editor" else False
        for step in result.get("steps", []):
            print(f"  {step['step']:>2} {step['operation']:<10} {step['action'][:60]!r:<64} {step.get('text') or ''}")
        row = {
            "task": task["name"],
            "status": result.get("status"),
            "verified": verified,
            "actions": len(result.get("steps", [])),
            "model_calls": result.get("model_calls"),
            "seconds": round((result.get("elapsed_ms") or 0) / 1000, 1),
            "final_url": result.get("final_url"),
            "reason": result.get("reason"),
            "verification": (result.get("verification") or {}).get("scores"),
            "tokens": (result.get("cost") or {}).get("input_tokens"),
            "usd": (result.get("cost") or {}).get("usd"),
        }
        print(json.dumps(row, ensure_ascii=False), flush=True)
        rows.append(row)
    print(f"\n### backend={BACKEND}")
    print(f"{'task':<16} {'status':<18} {'verified':<9} {'actions':>7} {'calls':>6} {'secs':>7}")
    for r in rows:
        status = r["status"] or ""
        calls = r["model_calls"] or 0
        print(f"{r['task']:<16} {status:<18} {str(r['verified']):<9} {r['actions']:>7} {calls:>6} {r['seconds']:>7}")


if __name__ == "__main__":
    main()
