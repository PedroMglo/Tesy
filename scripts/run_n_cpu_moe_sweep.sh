#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 MODEL.gguf OUTPUT_ROOT" >&2
  exit 2
fi

cat >&2 <<'EOF'
STATIC_NO_GO_N_CPU_MOE_FIT_CONFLICT

The pinned llama.cpp cannot safely execute the retired sweep semantics:
--fit on plus --n-cpu-moe N installs user tensor_buft_overrides before the
fitter runs. If fitting is required, common_fit_params aborts and the server
can continue into an oversized CUDA allocation.

The failed campaign results/n-cpu-moe-sweep-20260923T220215Z is preserved.
Do not retry this runner or reuse that output root.

Use:
  scripts/run_n_cpu_moe_capacity_pareto.sh --capacity-only MODEL.gguf NEW_OUTPUT_ROOT
EOF

exit 1
