# C44 profiler trace environment failure

- Objective/base: profile the C15 CPU wave intervals using C43's valid original and C15 plain 513-ID receipts as immutable references. Frozen at `0179cdbb5a6ce80ddddf2034114788677b011578` with E18/CPU100 guards.
- Observed: `--trace=nvtx,cuda` changed the runner's allowlisted environment by adding two `libnvperf` preload libraries and `CUDA_INJECTION64_PATH`. The identity gate stopped before idle/model/API. The Nsight report only records this failure; no wave intervals or physical model time can be claimed.
- Model-free discrimination: the earlier `--trace=nvtx` probe showed exactly one copy of the two frozen NVTX libraries in parent/child. A scoped `--trace=nvtx,cuda` probe reproduced the extra CUDA libraries and variable. The prior test used the wrong trace mode, which explains why C44 preflight missed this.
- Decision: preserve C44 `FAIL_HARNESS_PROFILER_TRACE_ENV_NO_MODEL`. A new C45 protocol can use NVTX-only because the frozen metric is CPU NVTX interval occupancy; CUDA kernel traffic is outside this gate. Same model, binary, input, resources and C43 references. No default change; C15 profiled model remains NOT_RUN.
