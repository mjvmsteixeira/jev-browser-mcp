#!/usr/bin/env bash
# Diagnostics for everything the browser agent needs. Read-only: reports, never fixes.
# Each line is "OK|WARN|FAIL <area>: <detail>".
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${JEV_CDP_PORT:-9333}"
MODEL="${TEXT_MODEL:-jev-agent}"
VAULT_READ="${JEV_VAULT_READ:-$HOME/vault/vault-read.sh}"
VAULT_PATH="${JEV_VAULT_PATH:-secret/ai/typesafe}"
CHROME="${JEV_CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

say() { printf '%s %s: %s\n' "$1" "$2" "$3"; }

command -v uv >/dev/null && say OK uv "$(uv --version)" || say FAIL uv "not on PATH; the server cannot start"

[ -x "$CHROME" ] && say OK chrome "binary found" || say FAIL chrome "not found at $CHROME (set JEV_CHROME)"
if curl -s --max-time 2 "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
  say OK cdp "dedicated Chrome answering on port $PORT"
else
  say WARN cdp "nothing on port $PORT; the server starts Chrome on the first call"
fi

if curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  if curl -s http://127.0.0.1:11434/api/tags | grep -q "\"$MODEL"; then
    # /api/show returns parameters as text ("num_ctx    16384"), not JSON.
    ctx=$(curl -s http://127.0.0.1:11434/api/show -d "{\"model\":\"$MODEL\"}" \
      | python3 -c 'import json,sys,re; p=json.load(sys.stdin).get("parameters") or ""; m=re.search(r"num_ctx\s+(\d+)", p); print(m.group(1) if m else "")' 2>/dev/null)
    if [ -n "$ctx" ] && [ "$ctx" -le 32768 ] 2>/dev/null; then
      say OK ollama "model $MODEL present (num_ctx=$ctx)"
    else
      say WARN ollama "model $MODEL has no reduced num_ctx; with the default context it falls back to CPU and times out — run scripts/setup-ollama.sh"
    fi
  else
    say FAIL ollama "model $MODEL missing; run $ROOT/scripts/setup-ollama.sh (without it the agent cannot type into fields)"
  fi
else
  say FAIL ollama "daemon not answering on 11434; field text will fail"
fi

KEY="${TYPESAFE_API_KEY:-}"
SOURCE="environment"
if [ -z "$KEY" ] && [ -x "$VAULT_READ" ]; then
  KEY=$("$VAULT_READ" "$VAULT_PATH" api_key 2>/dev/null)
  SOURCE="Vault ($VAULT_PATH)"
  [ "$KEY" = "null" ] && KEY=""
fi
if [ -n "$KEY" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://api.typesafe.ai/v1/models -H "Authorization: Bearer $KEY")
  if [ "$code" = "200" ]; then
    say OK typesafe "valid key, read from $SOURCE → decisions on Jev"
  else
    say FAIL typesafe "the key from $SOURCE was rejected (HTTP $code); run $ROOT/scripts/store-typesafe-key.sh"
  fi
else
  say WARN typesafe "no key → decisions on the local model, slower and without DONE verification"
fi

pid=$(pgrep -f "jev-browser-mcp" | head -1)
if [ -n "$pid" ]; then
  # lstart comes in the system language and macOS date cannot parse it; etime is immune to that.
  started_at=$(ps -p "$pid" -o etime= | python3 -c '
import sys, time
raw = sys.stdin.read().strip()
days, _, rest = raw.partition("-")
if not rest:
    days, rest = "0", raw
parts = [int(x) for x in rest.split(":")]
elapsed = int(days) * 86400 + sum(p * 60**i for i, p in enumerate(reversed(parts)))
print(int(time.time()) - elapsed)' 2>/dev/null)
  commit_at=$(cd "$ROOT" && git log -1 --format=%ct 2>/dev/null)
  if [ -n "$started_at" ] && [ -n "$commit_at" ] && [ "$started_at" -lt "$commit_at" ] 2>/dev/null; then
    say WARN server "the process (pid $pid) started before the last commit ($(date -r "$commit_at" "+%d/%m %H:%M")); reconnect in /mcp, since it reloads neither code nor secrets"
  else
    say OK server "running (pid $pid), newer than the last commit"
  fi
else
  say OK server "no process in memory; starts on the next call"
fi
