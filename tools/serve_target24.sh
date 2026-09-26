#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# The same server flags and artifact used by task120b-stream24-eval01.
# The user scope enforces the host-memory and zero-swap limits.
exec systemd-run --user --scope \
  --property=MemoryMax=18G --property=MemorySwapMax=0 \
  env LLAMA_MOE_STREAM_NO_PRELOAD=1 \
  ./backends/streaming/build-gcc15/bin/llama-server \
  -m /home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf \
  --host 127.0.0.1 --port 18367 \
  -ngl 8 -c 4096 -np 1 -b 256 -ub 32 -t 8 -tb 8 \
  --no-warmup --no-cache-prompt -lv 3 \
  --no-repack --no-op-offload --direct-io \
  --moe-stream-cache 24s --moe-stream-io-threads 4 --moe-stream-direct \
  --chat-template-kwargs '{"reasoning_effort":"medium"}'
