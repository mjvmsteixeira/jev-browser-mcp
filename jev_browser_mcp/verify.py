"""Second opinion on DONE. jev's own AGENTS.md says a DONE choice is not proof of success, and in
our benchmark both backends claimed DONE with a filter unset. These Noul questions re-read the final
page against the goal and return calibrated yes-probabilities."""

import os

import httpx

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
THRESHOLD = float(os.environ.get("JEV_VERIFY_THRESHOLD", "0.7"))
TEXT_LIMIT = 20000
QUESTIONS = {
    "all_requirements": {
        "type": "noul",
        "instructions": "Every requirement in the goal is visibly satisfied on this page.",
        "criteria": {
            "true": "Every requested value, filter, option and result asked for in the goal is visible here",
            "false": "Any requested value, filter or option is missing, left at its default, or not visible",
        },
    },
    "right_page": {
        "type": "noul",
        "instructions": "This page is the destination the goal asked to reach.",
    },
    "nothing_left": {
        "type": "noul",
        "instructions": "No further browser action is needed to satisfy the goal.",
        "criteria": {
            "true": "The task is finished; nothing remains to click, type or submit",
            "false": "A step is still pending, such as submitting, confirming or applying a setting",
        },
    },
}


def verify(objective, url, title, text, *, client=httpx, timeout=30):
    """None when no key is configured; otherwise scores per question plus a pass/fail."""
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key or key == "local":
        return None
    body = {
        "model": os.environ.get("TYPESAFE_MODEL", "jev-latest"),
        "state": {"goal": objective, "url": url, "title": title, "page_text": (text or "")[:TEXT_LIMIT]},
        "questions": QUESTIONS,
    }
    try:
        response = client.post(ENDPOINT, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
    except httpx.HTTPError as error:
        return {"error": f"{type(error).__name__}", "passed": None}
    if response.is_error:
        return {"error": f"HTTP {response.status_code}", "passed": None}
    answers = response.json().get("answers", {})
    scores = {}
    for name in QUESTIONS:
        value = answers.get(name, {}).get("noul")
        if not isinstance(value, (int, float)):
            return {"error": f"missing answer for {name}", "passed": None}
        scores[name] = round(float(value), 3)
    failed = [name for name, value in scores.items() if value < THRESHOLD]
    return {
        "scores": scores,
        "threshold": THRESHOLD,
        "failed": failed,
        "passed": not failed,
        "usage": response.json().get("usage", {}),
    }
