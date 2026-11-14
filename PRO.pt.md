# Jev Browser Pro

*[English version](PRO.md)*

Este repositório é gratuito e tem licença MIT, e assim continua. O **Jev Browser Pro** é um pacote pago construído
por cima dele, para uma tarefa que o plugin gratuito não faz: **testes de regressão à tua própria aplicação web** antes de
cada merge.

## O que o Pro acrescenta

Descreves um percurso de utilizador em poucas linhas de TOML, por exemplo "pesquisa Lisboa, marca Cancelamento
gratuito, abre a Casa Flora, e o Book now tem de estar protegido". O Pro corre-o e devolve um relatório de passou ou
falhou. Não há seletores para manter: o agente de browser faz os cliques e **as tuas próprias verificações** decidem
cada passo. O agente dizer que terminou nunca conta.

```toml
name = "Demo stays: search, filter, open, booking is guarded"
base_url = "http://127.0.0.1:8800"
allowed_domains = ["127.0.0.1"]

[[step]]
goal = "Type Lisbon as the destination, tick Free cancellation and search. Stop when the results are visible."
path = "/index.html"
expect_url = "q=Lisbon"
expect_text = ["Results for Lisbon", "Casa Flora"]
expect_no_text = ["Rio Hostel", "No stays found"]

[[step]]
goal = "Open Casa Flora. Stop when its page is visible."
expect_text = ["Casa Flora", "Book now"]

[[step]]
goal = "Click Book now."
expect_status = "needs_confirmation"
expect_no_text = ["Booking confirmed"]
```

- **QA flows**: percursos em TOML, cada passo verificado pelo URL, por texto que tem ou não pode estar na página e pelo
  estado esperado.
- **Verificação das proteções**: prova que "Book now", "Apagar conta" ou "Finalizar encomenda" não podem ser clicados
  por um agente sem aprovação.
- **Corre a partir do agente, da shell ou da CI**: um executor num só ficheiro (só a biblioteca padrão do Python) que o
  agente guarda no teu projeto. Exit code 0 ou 1, com relatórios em Markdown e JSON.
- **Uma skill** que ensina o agente a escrever flows para a tua aplicação e a ler cada resultado.
- **Um site de demonstração e um flow de exemplo** que correm em menos de um minuto, receitas e resolução de
  problemas.
- **O servidor de browser incluído**: o código MIT deste repositório vem no pacote, com um guia de configuração passo
  a passo, por isso o Pro funciona sozinho.

## Gratuito vs Pro

| | Gratuito (este repositório) | Pro |
| --- | --- | --- |
| `browse_interactive`: lista de domínios, paragem antes de cliques irreversíveis, reverificação do `DONE`, limites | Sim | Sim, o mesmo código, incluído |
| QA flows em TOML, verificados pelas tuas regras | Não | Sim |
| Executor de flows para o agente, a shell e a CI | Não | Sim |
| Relatórios em Markdown e JSON | Não | Sim |
| Site de demonstração e flow de exemplo | Não | Sim |
| Agentes | Claude Code | Claude Code (outros agentes MCP stdio não testados) |
| Instalação | `/plugin install` | Um zip da Agensi, configurado à mão a partir do `SETUP.md` |
| Licença | MIT | Conteúdo Pro proprietário; servidor incluído em MIT |
| Preço | Gratuito | Compra única |

**De qual preciso?** Para o Claude Code preencher formulários e navegar em sites enquanto trabalhas, o plugin
gratuito chega. Para confirmar, depois de cada alteração, que um percurso da tua aplicação continua a funcionar, sem
escrever seletores, o Pro.

Não precisas dos dois. O Pro inclui o servidor de browser; se já tiveres o plugin gratuito, o executor de flows do
Pro usa-o.

## Como obter o Pro

O Pro vai ser vendido na [Agensi](https://agensi.io), um marketplace de skills para agentes, em compra única. **Ainda
não está listado.** Esta página vai ter o link para a listagem assim que for aprovada.

Queres saber quando sair? Segue este repositório (Watch → Custom → Releases) ou abre uma
[issue](https://github.com/mjvmsteixeira/jev-browser-mcp/issues).

## Limites, sem rodeios (nas duas edições)

- Sem iframes, shadow DOM, canvas, upload de ficheiros nem pop-ups.
- Formulários longos com muitos widgets próprios não são preenchidos de forma fiável num só passo.
- Com uma chave TypeSafe, o texto visível de cada página vai para a TypeSafe. Sem chave, tudo corre na tua máquina,
  mais devagar.
