---
description: Diagnoses the browser agent — dedicated Chrome, local model, TypeSafe key and the server in memory
---

Run the diagnostics and interpret the result for the user, in the user's language:

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.sh"`

Each line comes as `OK|WARN|FAIL <area>: <detail>`. In your answer:

- If there is a `FAIL`, give the concrete action for each one (the detail already says it) and don't say it is
  operational.
- `WARN` doesn't block use, but explain the consequence (for example: without a key, decisions are slower and there
  is no `DONE` verification).
- If everything is `OK`, say in one line which backend will be used and move on.

Don't fix anything unless the user asks. The two actions with side effects are storing the key
(`scripts/store-typesafe-key.sh`, which needs the key on the clipboard) and creating the local model
(`scripts/setup-ollama.sh`, which downloads/derives a model of several GB).
