#!/usr/bin/env bash
# Launch the jev-browser MCP server with keys from the local Vault (never from a .env file).
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
READ=/Users/mjvmst/vault/vault-read.sh

secret() {
  local value
  value=$("$READ" "$1" "$2" 2>/dev/null) || return 0
  [ "$value" != "null" ] && printf '%s' "$value"
}

export TYPESAFE_API_KEY="${TYPESAFE_API_KEY:-$(secret secret/ai/typesafe api_key)}"
export TYPESAFE_MODEL="${TYPESAFE_MODEL:-jev-latest}"
# Field values are generated locally by Ollama; page text never leaves the machine for this step.
export TEXT_MODEL_API_KEY="${TEXT_MODEL_API_KEY:-ollama}"
export TEXT_MODEL_BASE_URL="${TEXT_MODEL_BASE_URL:-http://127.0.0.1:11434/v1}"
export TEXT_MODEL="${TEXT_MODEL:-qwen2.5:3b}"
export TEXT_MODEL_REASONING="${TEXT_MODEL_REASONING:-none}"

exec /Users/mjvmst/.local/bin/uv run --quiet --directory "$DIR" jev-browser-mcp
