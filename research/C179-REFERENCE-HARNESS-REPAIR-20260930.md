# C179 — prove bounded entrypoint before canonical weights

C176/C177 ended before any weights process: policy byte SHA and inventory/runtime schema defects respectively. C178 collected a valid 60-second inventory and ran only sleep, which correctly failed the monitor's nonempty GGML mapping requirement. All attempts remain preserved; these are harness failures, not numerical or thermal failures.

C179 uses an independent harmless binary linked to GGML-base, no model or graph, and retains the strict mapping gate. Source inspection also found that expected ldd identity omitted linked GGML libraries outside backend_root whereas actual mapping identity included them. Expected identity now records those exact absolute paths/hashes. Missing or extra mappings continue to fail. The linked CUDA library is from the preserved same-pin C148 build; no dependency installation changed.

Twelve directed model-free tests passed. Full suite NOT_RUN. C179 freezes a real smoke followed by layer24 only, under the same FILE_PAGING/E20 policy, monitor and independent bitwise reference. Weights cannot launch if smoke fails. No tolerances change. Later GPU references require a new frozen family and a layer24 PASS.
