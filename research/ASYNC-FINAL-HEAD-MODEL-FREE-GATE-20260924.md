# Async final HEAD model-free gate, 2026-09-24

- Objective: execute the frozen async candidate's final local model-free gate before native CUDA build and physical campaign.
- Base commit: `768ccfd2a2f9e7b3da2ff61a3006c7d5e17f6e08`.
- Base tree: `f83370fb7be82706a076e7c9aa3fb8048278179c`.
- Evidence class: reproduced local static-tool failure; no physical performance measurement.
- Inputs: clean worktree; branch `research/mixed-residency-async-overlap-restacked-20260924`; origin tracking ref at the same commit; `.venv/bin/python` resolves to `/usr/bin/python3.14`; `tesy` resolves to this repository's `src/tesy/__init__.py`.
- Tests: branch/HEAD/tree/clean checks PASS; Python package path PASS; `bash -n` on bootstrap and async runner PASS; focused `ruff check` FAIL (`I001` at `src/tesy/mixed_residency_async_overlap.py:1`). `ruff check --diff` removes one extra blank line between the import block and `_ASYNC_GO_RATIO`. Global Ruff 0.15.16 and `.venv` Ruff 0.16.8 reproduce the failure.
- NOT_RUN: compileall, focused pytest, complete model-free suite, backend/model/input checks, physical-host doctor, native CUDA build, Stack #22 link, physical async campaign and automated campaign audit. These depend on the failed focused gate in the requested sequence.
- Separate CI: workflow_dispatch run 36019448672 for #10 at `49c992ec33f689791aa930b578631ee0b28f801c`; in progress at last observation.
- Alternatives: changing the frozen source in place would invalidate the specified HEAD/tree; ignoring Ruff would bypass the required model-free gate. Neither was selected.
- Decision: STOP before build and campaign. Preserve the failed candidate and its clean worktree.
- Failure and limitation: this is a lint failure only; it does not establish runtime incorrectness or performance. No async physical result exists from this attempt.
- Next discriminating gate: remove the extra blank line in a prospective candidate commit, freeze its new HEAD/tree, then rerun all model-free gates from the start. Only after PASS, continue with pinned inputs, physical-host checks, native build, Stack link and campaign.
