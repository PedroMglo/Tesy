#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

model="${1:?usage: run_task_eval.sh stock20b|target120b RUN_ID [tune|eval]}"
run_id="${2:?usage: run_task_eval.sh stock20b|target120b RUN_ID [tune|eval]}"
split="${3:-eval}"
case "$model" in stock20b|target120b) ;; *) exit 2 ;; esac
case "$split" in tune|eval) ;; *) exit 2 ;; esac

systemd-run --user --scope --property=MemoryMax=18G --property=MemorySwapMax=0 \
  python3 tools/run_task_server.py --run-id "$run_id" --model "$model" --split "$split"
