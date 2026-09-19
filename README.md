# jev-browser-mcp

Servidor MCP que expõe o [jev-ultrafast](https://github.com/browser-use/jev-ultrafast) ao Claude Code como uma tool com guardas: `browse_interactive`.

## Guardas

- `allowed_domains` obrigatório: `start_url`, links clicados e redireções fora da lista param a execução.
- Cliques com cara de irreversíveis (comprar, apagar, enviar, reservar…, PT/EN) param com `needs_confirmation`, exceto com `allow_irreversible: true`.
- Orçamento `max_steps` e `timeout_s` (verificado entre passos). Uma execução de cada vez.
- Chrome dedicado (porta 9333, perfil `~/.jev-browser/chrome-profile`), nunca o perfil pessoal. Telemetria do browser-harness desligada.
- Devolve `page_text_untrusted`; o agente navega, o Claude extrai e verifica.

## Setup

```bash
uv sync
# chave no Vault (key: api_key): copiar de console.typesafe.ai/keys e correr scripts/store-typesafe-key.sh
#   secret/ai/typesafe    -> TYPESAFE_API_KEY
# Texto dos campos: Ollama local (qwen2.5:3b) por defeito; TEXT_MODEL* para mudar.
claude mcp add --scope user jev-browser -- "$PWD/run.sh"
```

Variáveis: `JEV_CDP_PORT`, `JEV_PROFILE_DIR`, `JEV_CHROME`, `JEV_HEADLESS=1`, `TEXT_MODEL*`.
Regras de encaminhamento: skill global `~/.claude/skills/web-routing`.

## Testes

```bash
uv run pytest && uv run ruff check .
```

Offline, sem APIs pagas.
