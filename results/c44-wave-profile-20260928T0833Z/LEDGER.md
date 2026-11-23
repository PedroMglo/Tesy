# C44 profiler-only recovery

- New identity after C43 profiled arm stopped before model on duplicated Nsight injection. C43 original/C15 plain PASS receipts are immutable references. No outer LD_PRELOAD; Nsight supplies the frozen libraries once to parent and child.
- `--trace=nvtx,cuda` profiled launch at commit `0179cdbb5a6ce80ddddf2034114788677b011578` failed the relevant-environment gate before idle/model/API. The 169544 B Nsight report contains only the prelaunch error. Scoped model-free checks showed NVTX-only supplies the frozen two libraries, whereas NVTX+CUDA adds `libnvperf_target.so`, `libnvperf_host.so` and `CUDA_INJECTION64_PATH`. C44 remains `FAIL_HARNESS_PROFILER_TRACE_ENV_NO_MODEL`; C43 valid arms untouched. Next C45 NVTX-only trace under new identity.
