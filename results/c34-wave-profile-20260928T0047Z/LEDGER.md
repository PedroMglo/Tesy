# C34 bounded C15 wave trace

- Frozen 513-ID synthetic P12 8K cold prompt; original backend control, C15 plain, then C15 profiled only after gates. Greedy four-token output equality is a diagnostic bridge, not full-logit numerical fidelity. Profiler times are not performance results. Original C18 and C29 FAILs remain unchanged.
- Pre-measurement focused suite initially had five fixture errors: `tools.test_c9_server_admission` built a config without the now-required `explicit_env` field. The gate itself was unchanged; test fixture repaired before measurement freeze. No C34 model run had started.
