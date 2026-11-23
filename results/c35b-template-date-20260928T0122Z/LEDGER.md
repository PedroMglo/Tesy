# C35b template date diagnostic

- New campaign identity after C35 failed before idle/model due missing systemd scope in invocation. C35 decision preserved. Same embedded GGUF template patch and frozen two-arm date contrast; physical runs NOT_RUN at this checkpoint.
- `c35b-date-shift-control` (`c0560c7`): PASS_BRIDGE, first/second 2035/2179 prompt IDs, 52/26 completion tokens; changed date yielded ordered LCP35 and cache_n35. Request elapsed 286.632/290.446 s. CPU/GPU/NVMe max 95.125/62/53.85 C, GPU 5752 MiB, zero swap/OOM, no stop reason. Diagnostic only; C29 FAIL unchanged.
- `c35b-date-stable-candidate` (`7b550bf`): PASS_BRIDGE, ordered LCP2035, cache_n2036; first/second request 288.016/29.561 s. CPU/GPU/NVMe max 95.125/62/51.85 C, GPU5752 MiB, zero swap/OOM, no stop reason. Diagnostic second-request reduction 89.82% against shifted-date control; prompts differ by date.
- Decision: TEMPLATE_DATE_CAUSE_CONFIRMED_TESTED_SCOPE. C29/C34b/C35 FAILs preserved. M3 partial, M4 NOT_RUN, C15 model NOT_RUN. Next: C36 current-date 4096+128 bridge, then sustained session if gates pass.
