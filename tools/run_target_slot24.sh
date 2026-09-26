#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

run_id="${1:?usage: run_target_slot24.sh RUN_ID}"
model=/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf

systemd-run --user --scope --property=MemoryMax=18G --property=MemorySwapMax=0 \
  python3 tools/run_bounded.py \
  --run-id "$run_id" \
  --model-id gpt-oss-120b-mxfp4-gguf \
  --backend streaming \
  --variant gpu8-stream24-direct-no-repack-ub32-greedy256 \
  --workload workloads/m1_two_turns.txt \
  --cache-condition new-process-direct-experts-after-M2-run \
  --timeout-s 900 --max-rss-gib 17 --min-available-gib 6 --max-gpu-mib 7000 \
  --env LLAMA_MOE_STREAM_NO_PRELOAD=1 \
  --stdin-file workloads/m1_two_turns.txt \
  -- backends/streaming/build-gcc15/bin/llama-cli \
  -m "$model" -ngl 8 -c 4096 -b 256 -ub 32 -t 8 -tb 8 -n 256 \
  -s 42 --temp 0 --no-warmup --simple-io --no-display-prompt --no-repack \
  -lv 3 --moe-stream-cache 24s --moe-stream-io-threads 4 --moe-stream-direct
