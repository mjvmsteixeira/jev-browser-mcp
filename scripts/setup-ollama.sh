#!/usr/bin/env bash
# Creates the local model used for field text (and for decisions without a TypeSafe key).
# The base model's default context (256k) does not fit in GPU memory and falls back to CPU,
# which makes every call exceed jev's HTTP timeout. 16k keeps it fully on the GPU.
set -euo pipefail
BASE="${1:-qwen3-coder:30b-a3b-q4_K_M}"
ollama show "$BASE" >/dev/null
printf 'FROM %s\nPARAMETER num_ctx 16384\nPARAMETER temperature 0\n' "$BASE" | ollama create jev-agent -f -
ollama list | grep jev-agent
