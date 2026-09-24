---
description: Diagnostica o agente de browser — Chrome dedicado, modelo local, chave TypeSafe e servidor em memória
---

Corre o diagnóstico e interpreta o resultado para o utilizador:

!`bash "${CLAUDE_PLUGIN_ROOT}/../scripts/doctor.sh"`

Cada linha vem como `OK|AVISO|FALHA <área>: <detalhe>`. Na tua resposta:

- Se houver `FALHA`, indica a ação concreta de cada uma (o detalhe já a diz) e não digas que está operacional.
- `AVISO` não impede o uso, mas explica a consequência (por exemplo: sem chave, as decisões são mais lentas e não há verificação do `DONE`).
- Se estiver tudo `OK`, diz numa linha qual o backend que vai ser usado e segue em frente.

Não corrijas nada sem o utilizador pedir. As duas ações com efeitos são guardar a chave
(`scripts/store-typesafe-key.sh`, que precisa da chave na área de transferência) e criar o modelo local
(`scripts/setup-ollama.sh`, que descarrega/deriva um modelo de vários GB).
