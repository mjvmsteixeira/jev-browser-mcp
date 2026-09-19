#!/usr/bin/env bash
# Copy the key from console.typesafe.ai/keys, then run this. The key goes clipboard -> Vault via stdin,
# never through argv, shell history or chat. The clipboard is cleared afterwards.
set -euo pipefail
KEY="$(pbpaste | tr -d '[:space:]')"
[ -n "$KEY" ] || { echo "Clipboard is empty" >&2; exit 1; }
TOKEN=$(jq -r .root_token /Users/mjvmst/vault/vault-init.json)
printf '%s' "$KEY" | docker exec -i -e VAULT_ADDR=https://127.0.0.1:8200 -e VAULT_CACERT=/vault/tls/ca.pem \
  -e VAULT_TOKEN="$TOKEN" vault vault kv put secret/ai/typesafe api_key=- >/dev/null
printf '' | pbcopy
code=$(curl -s -o /dev/null -w '%{http_code}' https://api.typesafe.ai/v1/models \
  -H "Authorization: Bearer $(/Users/mjvmst/vault/vault-read.sh secret/ai/typesafe api_key 2>/dev/null)")
echo "Stored in secret/ai/typesafe. API check: HTTP $code"
