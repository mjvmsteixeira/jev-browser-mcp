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
# Texto dos campos: Ollama local (qwen3-coder:30b-a3b) por defeito; TEXT_MODEL* para mudar.
claude mcp add --scope user jev-browser -- "$PWD/run.sh"
```

Variáveis: `JEV_CDP_PORT`, `JEV_PROFILE_DIR`, `JEV_CHROME`, `JEV_HEADLESS=1`, `TEXT_MODEL*`.
Regras de encaminhamento: skill global `~/.claude/skills/web-routing`.

## Sem chave TypeSafe: decisor local

Sem `TYPESAFE_API_KEY` (ou com `JEV_DECISION_BACKEND=ollama`), as decisões do Jev são imitadas por um modelo
Ollama local (`JEV_DECISION_MODEL`, por defeito `qwen3-coder:30b-a3b-q4_K_M`) com output JSON restrito às opções.
Tudo fica na máquina. Custo: ~4–7 s por decisão contra ~0,5 s do Jev, e probabilidades não calibradas.
O resultado indica `decision_backend`. O `qwen2.5:3b` é rápido mas falha a gerar texto de campos.

## Verificação do `DONE`

O `DONE` do agente é uma opinião: no benchmark os dois backends o declararam com um filtro por aplicar.
Com a chave TypeSafe, cada `DONE` é re-avaliado com três perguntas Noul sobre a página final (requisitos
satisfeitos, página certa, nada pendente). Abaixo de `JEV_VERIFY_THRESHOLD` (0.7) o estado passa a
`unverified` e as probabilidades vêm em `verification`. Custa uma chamada (~$0,00002).

Medido em 2026-09-24: GitHub (`done` falso) 0,09 / 0,34 / 0,25 → apanhado; fixture 0,92 / 0,96 / 0,92 e
Google Flights 0,81 / 0,94 / 0,92 → mantidos como `done`.

## Resultados medidos (2026-09-24, `scripts/bench_hard.py`)

Sete tarefas, cada uma verificada de forma independente pelo URL e pelo texto da página final, nunca pelo `DONE` do agente.
Texto dos campos sempre no Ollama local (`jev-agent`); só o decisor muda.

| Tarefa | Jev (`jev-latest`) | Decisor local (qwen3-coder 30b-a3b) |
| --- | --- | --- |
| fixture de hotéis (2 filtros + abrir resultado) | ✅ 2,8 s | ❌ ciclo, 41 s |
| Google Flights (autocomplete + date picker) | ✅ 10,2 s | ❌ bloqueou, 110 s |
| GitHub (faceta + dropdown de ordenação) | ❌ `done` falso, 5,0 s | ✅ 66,8 s |
| the-internet dynamic loading (espera de 5 s) | ❌ desistiu, 5,0 s | ✅ 10,5 s |
| DemoQA (formulário longo) | ❌ orçamento interno do jev, 48,9 s | ❌ bloqueou, 191 s |
| TodoMVC (precisa da tecla Enter) | limite esperado, parou em 2,8 s | limite esperado, parou em 19,7 s |
| editor em iframe (não suportado) | ✅ parou correctamente, 1,5 s | ❌ `done` falso, 3,7 s |

Leitura: o Jev é 5 a 20 vezes mais rápido e acerta nas tarefas com widgets compostos; o modelo local aguenta esperas
assíncronas e dropdowns que o Jev falhou. Ambos produziram um `done` falso — por isso o resultado tem de ser sempre
verificado. Os dois falharam o formulário longo do DemoQA.

## Testes

```bash
uv run pytest && uv run ruff check .
```

Offline, sem APIs pagas.
