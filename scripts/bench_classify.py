"""The other way to use Jev: one structured decision inside code, no browser.

Triages alerts the way prumo-secops would, and reports accuracy against hand-written labels,
latency and cost. Run: uv run python scripts/bench_classify.py
"""

import json
import os
import time

import httpx

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
PRICE_PER_MTOK = 0.042

QUESTIONS = {
    "team": {
        "type": "choice",
        "instructions": "Which team should handle this alert?",
        "criteria": {
            "infra": "Host, disk, memory, network or hypervisor problems",
            "appsec": "Web application attacks, injection, auth abuse, suspicious requests",
            "sysadmin": "Accounts, permissions, patching, service configuration",
            "noise": "Expected behaviour, maintenance or a known false positive",
        },
    },
    "severity": {
        "type": "score",
        "instructions": "How severe is this for a multi-tenant SaaS serving municipalities?",
        "criteria": [
            "Informational, no action needed",
            "Needs attention during business hours",
            "Urgent, act now: customer impact or active compromise",
        ],
    },
    "escalate": {
        "type": "noul",
        "instructions": "Should this wake a human outside business hours?",
        "criteria": {
            "true": "Customer-facing outage, data exposure or an attack in progress",
            "false": "Can wait for the next business day",
        },
    },
}

ALERTS = [
    ("Wazuh rule 5710: 148 failed SSH logins for root from 203.0.113.7 in 60s on app-prod-02", "appsec", 2, True),
    ("Zabbix: /var on db-prod-01 at 91% (threshold 90%), growing 2%/day", "infra", 1, False),
    ("Wazuh 31103: SQL injection pattern in POST /api/requerimentos from 198.51.100.4", "appsec", 2, True),
    ("Zabbix: nightly backup job finished in 42min (usual 38min)", "noise", 0, False),
    ("Wazuh 5402: successful sudo to root by deploy user during scheduled 02:00 deploy window", "noise", 0, False),
    ("Fortigate: WAN1 down 4 minutes, failover to WAN2 completed, all tenants reachable", "infra", 1, False),
    ("Wazuh 87105: ransomware-like mass file rename in /srv/tenant-data/braga, 4200 files in 3 min", "appsec", 2, True),
    ("Zabbix: puma worker restarted on app-prod-03 after OOM, service recovered in 12s", "infra", 1, False),
]


def triage(alert, key, client):
    body = {"model": os.environ.get("TYPESAFE_MODEL", "jev-latest"), "state": alert, "questions": QUESTIONS}
    started = time.perf_counter()
    response = client.post(ENDPOINT, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=30)
    response.raise_for_status()
    result = response.json()
    return result, round((time.perf_counter() - started) * 1000)


def main():
    key = os.environ["TYPESAFE_API_KEY"]
    client = httpx.Client(http2=True)
    hits = {"team": 0, "severity": 0, "escalate": 0}
    tokens, latencies = 0, []
    for alert, team, severity, escalate in ALERTS:
        result, ms = triage(alert, key, client)
        answers = result["answers"]
        got_team = answers["team"]["choice"]
        got_severity = answers["severity"]["score"]
        got_escalate = answers["escalate"]["noul"]
        hits["team"] += got_team == team
        hits["severity"] += abs(got_severity - severity) <= 0.5
        hits["escalate"] += (got_escalate >= 0.5) == escalate
        tokens += result.get("usage", {}).get("input_tokens", 0)
        latencies.append(ms)
        print(
            f"{ms:5}ms  team={got_team:<9}(esperado {team:<9}) "
            f"sev={got_severity:4.2f}(esperado {severity}) escalar={got_escalate:4.2f}(esperado {escalate})"
            f"  | {alert[:60]}"
        )
    n = len(ALERTS)
    latencies.sort()
    print(
        json.dumps(
            {
                "alerts": n,
                "accuracy": {k: f"{v}/{n}" for k, v in hits.items()},
                "median_ms": latencies[n // 2],
                "input_tokens": tokens,
                "usd_total": round(tokens * PRICE_PER_MTOK / 1_000_000, 6),
                "usd_per_10k_alerts": round(tokens / n * 10000 * PRICE_PER_MTOK / 1_000_000, 2),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
