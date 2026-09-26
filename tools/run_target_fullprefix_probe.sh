#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:?usage: run_target_fullprefix_probe.sh plain|stream RUN_ID}"
run_id="${2:?usage: run_target_fullprefix_probe.sh plain|stream RUN_ID}"
model=/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf

case "$mode" in
  plain)
    backend=streaming-reference
    variant=cpu0-plain-mmap-noprefetch-fullprefix-ub32
    runner=(--env TESY_LOGITS_PLAIN_MMAP=1 --env TESY_MMAP_NO_PREFETCH=1)
    command=(tools/logits_probe_reference_cuda "$model" plain 0 "results/${run_id}.f32" no-repack 32)
    ;;
  stream)
    backend=streaming
    variant=cpu0-stream24-direct-fullprefix-ub32
    runner=(--env TESY_LOGITS_STREAM_SLOTS=24 --env LLAMA_MOE_STREAM_NO_PRELOAD=1)
    command=(tools/logits_probe_streaming_cuda_slot24 "$model" stream 0 "results/${run_id}.f32" no-repack 32 direct-loader)
    ;;
  *) exit 2 ;;
esac

systemd-run --user --scope --property=MemoryMax=18G --property=MemorySwapMax=0 \
  python3 tools/run_bounded.py \
  --run-id "$run_id" --model-id gpt-oss-120b-mxfp4-gguf \
  --backend "$backend" --variant "$variant" \
  --workload fixed-harmony-fullprefix \
  --cache-condition new-process-plain-mmap-or-direct-experts-existing-system-cache \
  --timeout-s 600 --max-rss-gib 17 --min-available-gib 6 --max-gpu-mib 7000 \
  "${runner[@]}" -- "${command[@]}"
