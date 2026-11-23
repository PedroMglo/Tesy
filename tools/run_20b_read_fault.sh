#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ulimit -c 0
cc -shared -fPIC -O2 -Wall -Wextra -o tools/libfault_pread.so tools/fault_pread.c

run_id="${1:?usage: run_20b_read_fault.sh RUN_ID}"
model=/home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf

systemd-run --user --scope --property=MemoryMax=9G --property=MemorySwapMax=0 \
  python3 tools/run_bounded.py \
  --run-id "$run_id" --model-id gpt-oss-20b-mxfp4-gguf \
  --backend streaming --variant gpu8-stream16-direct-injected-eio \
  --workload fixed-eight-token-arithmetic-smoke \
  --cache-condition new-process-direct-experts-existing-system-cache \
  --timeout-s 180 --max-rss-gib 8.5 --min-available-gib 6 --max-gpu-mib 7000 \
  --env LLAMA_MOE_STREAM_NO_PRELOAD=1 \
  --env "LD_PRELOAD=$PWD/tools/libfault_pread.so" \
  -- backends/streaming/build-gcc15/bin/llama-cli \
  -m "$model" -ngl 8 -c 4096 -b 256 -ub 32 -t 8 -tb 8 \
  -n 8 -s 42 --temp 0 -st -p 'Reply with the sum of 7 and 5, then stop.' \
  --no-warmup --simple-io --no-display-prompt --no-repack -lv 3 \
  --moe-stream-cache 16s --moe-stream-io-threads 4 --moe-stream-direct
