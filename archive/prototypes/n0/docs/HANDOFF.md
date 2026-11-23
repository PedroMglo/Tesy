# Tesy N0 engineering handoff

Date: 2026-09-23, Europe/Lisbon. The current outcome is a tested development
foundation, NOT a completed optimized MoE runtime. See IMPLEMENTATION_STATUS.md.

## Git and publication

The remote PedroMglo/Tesy was read using the connected GitHub API. It had no
branches/commits. Issue #1 was already present. Creating a dedicated branch from
main returned HTTP 409: Git Repository is empty. The connector's create-commit
surface requires a parent commit and does not expose a root commit. Network Git
access from the development container failed DNS resolution. No main write,
merge, force push or model download was made to circumvent these constraints.

The deliverable Git bundle contains a complete new local root history on
research/tesy-n0-foundation-20260923, with no submodules. The local worktree has
an origin URL but no upstream because no remote ref was published. Checksums and
final HEAD/tree are supplied with the downloadable delivery manifest. They are
not inferred from this document's own later commit.

### Remote initialization observed during final reconciliation

A later API read found `main` at 445405f619d09f0df5870b8c0238658f4b430ab7 and
`research/novelty-runtime-foundation-20260923` at
41661533bfd0e91251f6840a4b8dc3a2d528d27f, tree
1a03d2098bd4ee4673b1e78dc418f09025c6f065. The latter added the project
AGENTS.md, README, N0 charter/novelty map and backend ADR. Those rules were read
before reconciliation. They are compatible with this implementation's scope.

The publication branch was successfully created from that exact remote base:
`research/tesy-causal-residency-20260923`. Publication uses a new commit parented
to the actual remote base, not an unrelated-history merge. Keep its existing
AGENTS.md, charter, novelty map and backend ADR. README changes document the
commands that are actually implemented rather than aspirational command names.
The initial empty-repository error remains historical, not a current permanent
blocker. No main write, merge or force push is authorized.

The original local root history and bundle remain provenance of development
before the remote existed. Do not push that unrelated root over the now-published
repository. Use the publication branch for continuation:

```bash
git clone --branch research/tesy-causal-residency-20260923 \
  https://github.com/PedroMglo/Tesy.git
cd Tesy
```

Remote readback and final commit identities are provided in the completion
receipt, not inferred here. Tests refer to the exact implementation tree noted
in research/n0/VALIDATION.md; publication must verify unchanged source bytes.

## Reproduce this phase before using a model

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps --no-build-isolation -e .
bash scripts/test.sh
cmake -S . -B build-sanitized -DCMAKE_BUILD_TYPE=Debug -DTESY_SANITIZE=ON
cmake --build build-sanitized --parallel 2
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 \
  ctest --test-dir build-sanitized --output-on-failure
tesy doctor
```

Run in the repository root because default lock/profile paths are root-relative.
The native self-test generates only tiny synthetic F32 experts. Read
MODELOS_A_INSTALAR.md before the first optional stock model run. The script
scripts/build_stock.sh builds an external dependency explicitly, not silently as
part of tests. No stock/CUDA build or real-model run was validated here.

## Next discriminating engineering gate

1. Inspect the actual laptop, storage and software. Build the locked stock
   llama.cpp independently; verify the chosen GGUF hash/architecture. Preserve a
   controlled stock baseline. A missing GPU/toolchain/model remains NOT_RUN.
2. Locate native qwen3moe routing at the pinned source. Instrument the real router
   without changing its decisions or inserting Python callbacks in the hot path.
   Derive expert spans from GGUF layout and all component matrices; a metadata
   parser and naming heuristic alone cannot determine ready-to-load expert spans.
3. Emit bounded native route events with position/layer/expert/order and decision
   availability. Record source/model/binary identities. Independently verify
   trace chronology and collection overhead. Do not feed future reference routes
   to the candidate. Add a real collector test before claiming live tracing.
4. Calibrate byte/cost replay against the observed backend. Keep CPU fallback,
   overlapping copies, tensor layout, shared weights and KV budgets explicit.
   The current serial simulator does not model them and cannot select a production
   scheduler from hit rate alone.
5. Introduce the smallest demand-only quantized expert-residency integration.
   Keep tokenizer, template, natural routing, attention, KV and output on stock
   semantics. The standalone native F32 store is ownership/I/O infrastructure,
   not a quantized GGML backend and not yet suitable to run a full model.
6. Validate routing, aggregation, logits, tokens and required target state against
   an independent reference before timing. Freeze a numerical contract before
   comparing CPU/GPU arithmetic. Do not weaken exactness after a mismatch.
7. Only after a working demand path: causal prefetch with wasted-byte accounting;
   after measured benefit: bounded speculative windows. Sequential target traces
   cannot establish accepted prefixes or the union of rejected draft experts.

## Decisions not to undo silently

- Novelty UNESTABLISHED. DALI/SeqMoE/MoE-SpeQ substantially overlap broad claims.
- Approximate routing or expert dropping changes the target and is not this mode.
- No WQ/WV, dynamic precision, mandatory 72B route or gates imported from MOSAIC.
- MEASURED_REFERENCE bandwidth is not a hard maximum.
- Native pread bytes and simulated loads are not physical NVMe traffic.
- The transition-policy synthetic regression increased cache hits but also H2D
  requests; preserve it. It is not a full-model speedup nor a global impossibility.
- Linux trusted directories and immutable input files are required. Do not turn
  canonical checks into a claim of security against hostile directory renames.
- The stock launcher does not provide CPU thermal/power telemetry or formal
  measurement. It does not prove laptop-safe behavior until tested on that host.

## Review quality and remaining limitations

This task used one implementation writer and tests; it did not run independent
human or separate-agent reviews. No such review is claimed. Production CUDA
ownership, real expert packing, fork maintenance, actual model memory, prefill,
sustained laptop thermals and end-to-end usefulness remain open.

The first usable model guide is deliberately one artefact, not bulk installation
of 100B+ models. Do not confuse a working stock handoff with the Tesy contribution.
