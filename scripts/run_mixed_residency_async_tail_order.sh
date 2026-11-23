#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 MODEL.gguf HISTOGRAM.json OUTPUT_ROOT" >&2
  exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export TESY_ASYNC_SAMPLES=81
export TESY_ASYNC_TAIL_ORDER=1

exec bash "$root/scripts/run_mixed_residency_async_overlap.sh" "$@"
