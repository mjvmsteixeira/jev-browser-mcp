#!/usr/bin/env bash
# Diagnostics for everything the browser agent needs. Read-only: reports, never fixes.
# Each line is "OK|AVISO|FALHA <área>: <detalhe>".
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${JEV_CDP_PORT:-9333}"
MODEL="${TEXT_MODEL:-jev-agent}"
VAULT_READ="${JEV_VAULT_READ:-$HOME/vault/vault-read.sh}"
VAULT_PATH="${JEV_VAULT_PATH:-secret/ai/typesafe}"
CHROME="${JEV_CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

say() { printf '%s %s: %s\n' "$1" "$2" "$3"; }

command -v uv >/dev/null && say OK uv "$(uv --version)" || say FALHA uv "não está no PATH; o servidor não arranca"

[ -x "$CHROME" ] && say OK chrome "binário encontrado" || say FALHA chrome "não existe em $CHROME (define JEV_CHROME)"
if curl -s --max-time 2 "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
  say OK cdp "Chrome dedicado a responder na porta $PORT"
else
  say AVISO cdp "nada na porta $PORT; o servidor arranca o Chrome na primeira chamada"
fi

if curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  if curl -s http://127.0.0.1:11434/api/tags | grep -q "\"$MODEL"; then
    # /api/show devolve os parâmetros como texto ("num_ctx    16384"), não como JSON.
    ctx=$(curl -s http://127.0.0.1:11434/api/show -d "{\"model\":\"$MODEL\"}" \
      | python3 -c 'import json,sys,re; p=json.load(sys.stdin).get("parameters") or ""; m=re.search(r"num_ctx\s+(\d+)", p); print(m.group(1) if m else "")' 2>/dev/null)
    if [ -n "$ctx" ] && [ "$ctx" -le 32768 ] 2>/dev/null; then
      say OK ollama "modelo $MODEL presente (num_ctx=$ctx)"
    else
      say AVISO ollama "modelo $MODEL sem num_ctx reduzido; com o contexto por omissão cai para CPU e estoura o timeout — corre scripts/setup-ollama.sh"
    fi
  else
    say FALHA ollama "modelo $MODEL não existe; corre $ROOT/scripts/setup-ollama.sh (sem ele o agente não escreve em campos)"
  fi
else
  say FALHA ollama "daemon não responde em 11434; o texto dos campos falha"
fi

KEY="${TYPESAFE_API_KEY:-}"
SOURCE="ambiente"
if [ -z "$KEY" ] && [ -x "$VAULT_READ" ]; then
  KEY=$("$VAULT_READ" "$VAULT_PATH" api_key 2>/dev/null)
  SOURCE="Vault ($VAULT_PATH)"
  [ "$KEY" = "null" ] && KEY=""
fi
if [ -n "$KEY" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://api.typesafe.ai/v1/models -H "Authorization: Bearer $KEY")
  if [ "$code" = "200" ]; then
    say OK typesafe "chave válida, lida do $SOURCE → decisões no Jev"
  else
    say FALHA typesafe "a chave do $SOURCE foi recusada (HTTP $code); corre $ROOT/scripts/store-typesafe-key.sh"
  fi
else
  say AVISO typesafe "sem chave → decisões no modelo local, mais lento e sem verificação do DONE"
fi

pid=$(pgrep -f "jev-browser-mcp" | head -1)
if [ -n "$pid" ]; then
  # lstart vem no idioma do sistema e o date do macOS não o reconhece; etime é imune a isso.
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
    say AVISO servidor "o processo (pid $pid) arrancou antes do último commit ($(date -r "$commit_at" "+%d/%m %H:%M")); reconecta em /mcp, porque não recarrega código nem segredos"
  else
    say OK servidor "a correr (pid $pid), mais recente que o último commit"
  fi
else
  say OK servidor "nenhum processo em memória; arranca na próxima chamada"
fi
