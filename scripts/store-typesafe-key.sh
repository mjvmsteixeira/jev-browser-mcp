#!/usr/bin/env bash
# Copy the key from console.typesafe.ai/keys, then run this. The key goes clipboard -> Vault via stdin,
# never through argv, shell history or chat. It is validated against the API before being stored.
set -euo pipefail
KEY="$(pbpaste | tr -d '[:space:]')"
[ -n "$KEY" ] || { echo "Clipboard is empty: copy the key from console.typesafe.ai/keys first" >&2; exit 1; }
code=$(curl -s -o /dev/null -w '%{http_code}' -K - https://api.typesafe.ai/v1/models <<<"header = \"Authorization: Bearer $KEY\"")
if [ "$code" != "200" ]; then
  echo "TypeSafe rejected the clipboard content (HTTP $code, ${#KEY} chars). Nothing stored." >&2
  echo "Copy the API key itself from console.typesafe.ai/keys, not this command." >&2
  exit 1
fi
TOKEN=$(jq -r .root_token /Users/mjvmst/vault/vault-init.json)
printf '%s' "$KEY" | docker exec -i -e VAULT_ADDR=https://127.0.0.1:8200 -e VAULT_CACERT=/vault/tls/ca.pem \
  -e VAULT_TOKEN="$TOKEN" vault vault kv put secret/ai/typesafe api_key=- >/dev/null
printf '' | pbcopy
echo "Key valid (HTTP 200) and stored in secret/ai/typesafe. Clipboard cleared."
