# jev-browser-mcp

Servidor MCP que dá ao Claude Code um agente de browser: uma tool, `browse_interactive`, que abre um Chrome
dedicado e executa tarefas interativas na web (preencher formulários, aplicar filtros, autocomplete, date
pickers, SPAs).

Por dentro usa o [jev-ultrafast](https://github.com/browser-use/jev-ultrafast) da Browser Use, que em cada
passo lê a página, numera os elementos com que se pode interagir e pede ao modelo [Jev](https://docs.typesafe.ai)
da TypeSafe uma operação (`CLICK`, `TYPE_TEXT`, `SELECT`, `SCROLL`, `WAIT`, `DONE`, `BLOCKED`) e o número do
elemento. O modelo nunca gera seletores nem coordenadas: só escolhe um número de uma lista que o código lhe deu.

Este repositório é a camada que falta à volta disso: guardas de segurança, verificação do resultado,
contabilidade de custos e as correções dos defeitos que apareceram a testar a sério.

## O que acrescenta ao jev-ultrafast

| | Porquê |
| --- | --- |
| **Lista de domínios permitida** | Obrigatória. O URL inicial, os links clicados e as redireções fora da lista param a execução |
| **Paragem antes de ações irreversíveis** | Comprar, apagar, enviar, reservar e semelhantes (PT e EN) devolvem `needs_confirmation` em vez de clicar |
| **Verificação do `DONE`** | O agente afirmar que terminou não é prova. Três perguntas Noul re-avaliam a página final |
| **Guarda de ciclos** | Pára com a mesma operação repetida 4 vezes no mesmo elemento, ou 20 s de espera seguida |
| **Operação Enter** | O jev não tem tecla Enter, e há campos que só submetem assim. O wrapper injeta `PRESS_ENTER` |
| **Retomas** | Se o agente desiste com a página ainda a mudar, dá-se-lhe nova oportunidade (2x); uma resposta malformada do modelo é repetida em vez de abortar a tarefa |
| **Orçamentos** | `max_steps` e `timeout_s`, e uma execução de cada vez |
| **Chrome dedicado** | Porta 9333, perfil próprio, sem as sessões pessoais; telemetria do browser-harness desligada |
| **Custo por tarefa** | Tokens de entrada e dólares em cada resultado |
| **Modo local** | Sem chave TypeSafe, as decisões passam a correr num modelo Ollama na máquina |

## Instalação

```bash
uv sync
scripts/setup-ollama.sh              # cria o modelo jev-agent (contexto 16k) para o texto dos campos
scripts/store-typesafe-key.sh        # copia a chave de console.typesafe.ai/keys e guarda-a no Vault
claude mcp add --scope user jev-browser -- "$PWD/run.sh"
```

O `run.sh` lê a chave do Vault (`secret/ai/typesafe`) sempre que o servidor arranca; nunca há chaves em ficheiros
do projeto. Se o servidor tiver arrancado antes de a chave existir, reconecta em `/mcp`.

Variáveis: `JEV_CDP_PORT`, `JEV_PROFILE_DIR`, `JEV_CHROME`, `JEV_HEADLESS=1`, `JEV_DECISION_BACKEND`,
`JEV_DECISION_MODEL`, `JEV_VERIFY_THRESHOLD`, `JEV_MODEL_TIMEOUT`, `TEXT_MODEL*`.

## Utilização

Pede em linguagem natural; a skill global `~/.claude/skills/web-routing` decide quando usar esta tool em vez de
`WebFetch`, `WebSearch` ou context7 (ler uma página ou pesquisar é mais rápido e barato por esses caminhos).

```
"Na minha app em http://localhost:3000, vê se consigo pesquisar 'Braga' e aplicar o filtro 'Ativos'."
```

Resultado: `status`, `reason`, `final_url`, `title`, `page_text_untrusted` (texto da página final, de onde se
extrai a resposta), `steps`, `verification`, `cost` e `decision_backend`.

Estados: `done` (já re-verificado com o Jev), `unverified` (o agente disse que acabou mas a verificação
discordou), `blocked`, `stalled`, `timeout`, `step_budget`, `needs_confirmation`, `domain_blocked`, `error`.

O texto devolvido é conteúdo da web: são dados, nunca instruções.

## Verificação do `DONE`

No benchmark, os dois modelos declararam `DONE` com um requisito por cumprir. Por isso, cada `DONE` é
re-avaliado com três perguntas de sim/não sobre a página final (requisitos satisfeitos, página certa, nada
pendente). Abaixo de `JEV_VERIFY_THRESHOLD` (0.7) o estado passa a `unverified`.

Medido a 2026-09-24: GitHub, que era um `done` falso, deu 0,09 / 0,34 / 0,25 e foi apanhado; a fixture de
hotéis deu 0,92 / 0,96 / 0,92 e o Google Flights 0,81 / 0,94 / 0,92, ambos mantidos como `done`.

## Resultados medidos (2026-09-24, `scripts/bench_hard.py`)

Sete tarefas, cada uma verificada de forma independente pelo URL e pelo texto da página final, nunca pelo
`DONE` do agente. O texto dos campos corre sempre no Ollama local; só o decisor muda.

| Tarefa | Jev (`jev-latest`) | Decisor local (qwen3-coder 30b-a3b) |
| --- | --- | --- |
| Fixture de hotéis (2 filtros + abrir resultado) | ✅ 3,7 s | ❌ ciclo detetado, 15 s |
| Google Flights (autocomplete + date picker) | ✅ 8,4 s | ❌ bloqueou, 48 s |
| GitHub (faceta + dropdown de ordenação) | ✅ 4,8 s | ❌ bloqueou, 21 s |
| the-internet, carregamento assíncrono de 5 s | ⚠️ objetivo cumprido, mas o agente deu-se por vencido | ✅ 7,1 s |
| TodoMVC (só submete com Enter) | ⚠️ criou os todos e filtrou; não completou um deles | ❌ ciclo detetado, 18 s |
| DemoQA (formulário longo) | ❌ esgotou o orçamento interno do jev (120 chamadas) | ❌ idem, 120 s |
| Editor dentro de iframe (não suportado) | ✅ parou correctamente, 3,4 s | ❌ `done` falso |

O Jev resolve 3 das 5 tarefas reais e chega ao objetivo numa quarta sem o reconhecer; é 5 a 10 vezes mais
rápido que o modelo local. Nenhum dos dois conclui o formulário longo do DemoQA. O modelo local continua a
ganhar nas esperas assíncronas.

Custo típico de uma tarefa de browser: 10 a 40 mil tokens de entrada, $0,0005 a $0,0017, 3 a 10 s. Para
comparação, `scripts/bench_classify.py` mede a outra forma de usar o mesmo modelo — uma decisão estruturada
dentro de código, sem browser — em $0,000022 e 0,3 s por item, com 21 de 24 respostas certas em 8 alertas.
Quando a decisão se repete dentro de um sistema, esse é o caminho certo; este servidor é para quando a
informação só existe atrás de cliques.

## Limites conhecidos

- Do jev-ultrafast: sem suporte a iframes, shadow DOM, uploads ou pop-ups (a tecla Enter passou a existir aqui).
- Do Jev: páginas muito grandes esgotam o contexto (o wrapper corta rótulos e limita opções de `select`, mas
  há casos que continuam a rebentar).
- Da verificação: quem verifica é o mesmo modelo que decidiu, e engana-se nos dois sentidos — no
  carregamento assíncrono deu 0,42 a uma página que já cumpria o objetivo. É um sinal, não uma prova.
- Formulários longos com muitos widgets ainda não foram concluídos por nenhum dos dois modelos.

## Segurança e privacidade

- O Chrome dedicado não tem as sessões pessoais; o snapshot ignora campos de password.
- Com o backend `typesafe`, o texto visível de cada página vai para a TypeSafe. Em páginas com dados pessoais
  de clientes, usa `JEV_DECISION_BACKEND=ollama`, e nada sai da máquina.
- Nunca usar em painéis de produção, consolas cloud, Vault, banca ou email.

## Testes e benchmarks: coisas diferentes

**Testes** (`uv run pytest && uv run ruff check .`) verificam este wrapper: guardas de domínio, paragem antes
de ações irreversíveis, orçamentos, deteção de ciclos, corte de rótulos, limite de opções, operação Enter,
verificação do `DONE`, contabilidade de custos, a tool e a camada do protocolo MCP. São offline, sem browser
nem APIs pagas, e **passam todos**. Se algum falhar, é um defeito.

**Benchmarks** (`scripts/bench_hard.py`, `scripts/bench_classify.py`) medem até onde o agente consegue ir em
sites reais. Fazem chamadas pagas e abrem o browser. As falhas na tabela abaixo **não são defeitos deste
repositório**: são o estado da arte dos modelos, e estão ali para se saber o que se pode prometer.
