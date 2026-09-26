#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

run_id="${1:?usage: run_target_gpu8_probe.sh RUN_ID 16|24|32}"
slots="${2:?usage: run_target_gpu8_probe.sh RUN_ID 16|24|32}"
case "$slots" in 16|24|32) ;; *) exit 2 ;; esac
model=/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf

systemd-run --user --scope --property=MemoryMax=18G --property=MemorySwapMax=0 \
  python3 tools/run_bounded.py \
  --run-id "$run_id" \
  --model-id gpt-oss-120b-mxfp4-gguf \
  --backend streaming \
  --variant "gpu8-stream${slots}-direct-prefix4-ub32" \
  --workload fixed-harmony-prefix4 \
  --cache-condition new-process-direct-experts-existing-system-cache \
  --timeout-s 600 --max-rss-gib 17 --min-available-gib 6 --max-gpu-mib 7000 \
  --env TESY_LOGITS_PREFIX_TOKENS=4 --env "TESY_LOGITS_STREAM_SLOTS=${slots}" \
  --env LLAMA_MOE_STREAM_NO_PRELOAD=1 \
  -- tools/logits_probe_streaming_cuda_slot24 "$model" stream 8 \
  "results/${run_id}.f32" no-repack 32 direct-loader
