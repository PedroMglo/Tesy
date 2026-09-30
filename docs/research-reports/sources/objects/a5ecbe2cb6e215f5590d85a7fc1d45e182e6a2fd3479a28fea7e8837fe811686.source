# N0 development validation — 2026-09-23

Classification: **DEVELOPMENT_ONLY / CPU_ONLY / SYNTHETIC**.
The N0 scope was committed before implementation in the local root history.
This report does not establish novelty, real-model exactness or speedup.

Implementation commit tested: `d03cb025378b3562398777455ddafbcfae132b17`.
Implementation tree: `fcd1870927339855301277633ce4981376854b4b`.
The subsequent documentation/CI commit does not change the implementation.
Final delivery HEAD/tree and checksums are recorded outside the tree to avoid
self-referential hash claims.

## Environment actually observed

Separate Linux development container, not the owner's laptop. Host CPU string:
AMD EPYC 9V74 80-Core Processor; five logical CPUs visible. MemTotal recorded by
`tesy doctor`: 6,236,913,664 bytes; cgroup memory.max: 4,294,967,296 bytes.
No nvidia-smi, nvcc or GPU was available. No real model was downloaded/opened.
Python 3.13.5, pytest 9.0.2, setuptools 82.0.1, GCC 14.2.0, CMake 3.31.6.

Reference laptop configuration comes from the owner, not this observation:
Ryzen AI 9 HX 370, RTX 4060 Laptop 8 GiB, 32 GiB RAM, Linux/NVMe.
No laptop bandwidth, temperatures, placement or throughput was measured here.

## Executed checks

- Final `bash scripts/test.sh`: **107 Python tests passed in 5.68 seconds**;
  Release CMake build succeeded; native CTest **1/1 passed**; Python compileall,
  shell syntax check and git diff --check succeeded.
- A separately configured Debug build with AddressSanitizer and UBSan succeeded;
  `ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 ctest` **1/1 passed**.
- Editable installation without dependency download/build isolation succeeded;
  `tesy --version`, CLI help, doctor, replay, union and transport planning ran.
- Native ldd inspection showed standard C/C++ libraries, no CUDA/LLM linkage.
- Tests include 243 exhaustive short fixed-size demand sequences against a
  separate LRU reference; 100 variable-size sequences across three policies;
  causal prefix invariance under future trace changes; truncated/overlapping/
  malformed GGUF fixtures; duplicate/non-finite JSON; bool/integer confusion;
  no-replace publication with 12 competing writers; stable-read mutation/path
  replacement; source hash/size errors and command/resource guard checks.
- The native self-test performs actual tiny-file reads, leases, bounded eviction,
  SwiGLU expert evaluation, source mutation/truncation and unchanged-output faults.
  Its compact F32 format is not GGUF and the fixtures are not an LLM.

Earlier development suites of 103 then 106 tests passed. The final additional
regression rejects a JSON publication larger than its readback limit *before*
creating any file; it does not turn a partial publication into a success.

## Retained command failure

A final sanitizer test command initially used `build-sanitized` before that
particular build directory existed. CTest exited with `Failed to change working
directory ... No such file or directory`; no native test ran in that invocation.
The failure log is retained. The directory was subsequently configured and built
explicitly, then the new CTest invocation passed. This is a development command
error, not a hidden model retry or proof that the failed command passed.

## Synthetic result: more hits did not mean fewer transfers

Fixed example: eight demands, route 0,1,0,1,0,1,2,2; three 64-byte experts;
GPU cache 64 bytes; RAM cache 128 bytes. Results are **simulated**:

| Policy | Demand GPU hits / 8 | Source request bytes | Total H2D payload bytes | Unused/evicted prefetch bytes |
|---|---:|---:|---:|---:|
| LRU | 1 | 192 | 448 | 0 |
| LFU | 1 | 192 | 448 | 0 |
| Causal transition | 4 | 192 | 512 | 64 |

The transition predictor improved demand-hit count but increased H2D requests
by 64 bytes. It uses only past observations, not future route lookup. Its
synchronous prefetch has no claimed overlap. This is a useful counterexample to
optimizing hit rate alone, not an end-to-end slowdown benchmark nor a general
rejection of all prefetch policies. No alternative was selected for production.

`union --k 3` includes a two-token tail and emits `acceptance_measured=false`.
The synthetic transport example emits `ESTIMATED_INFEASIBLE`, not hard NOGO,
because its bandwidth is an assumption. No speculative speedup is inferred.

## NOT_RUN / not implemented

- Ruff and Graphify: TOOL_UNAVAILABLE; not claimed passed.
- GitHub CI: workflow added with pinned action commits, REMOTE_NOT_RUN.
- External llama.cpp checkout/build, CUDA, real GGUF inference, live routing trace
  collection, bitwise full-model comparison and sustained laptop benchmarking:
  NOT_RUN_NETWORK_MODEL_AND_HOST_REQUIRED.
- Native cache integration with quantized GGML experts, CUDA demand/prefetch
  runtime, optimized chat and joint speculative controller: NOT_IMPLEMENTED.
- Independent human/separate-agent reviews: NOT_RUN; test coverage is not a
  substitute for those reviews.

## Evidence hashes

Raw logs and generated JSON remain outside Git and are included in the validation
ZIP delivered with the source/bundle. These SHA-256 identities refer to exact
captured bytes; none is a model hash or a claim of target-host performance.

| File | SHA-256 |
|---|---|
| `tesy-tests-final.log` | `bf87c456c3ca7fd3654e2019f2730bbd732923caabc799700569f7d3b0ff4a21` |
| `tesy-sanitize-final.log` | `7da134da1372f05120d8c252026bb6160856d902bf5e467f8526d24c5ca64715` |
| `tesy-sanitize-path-failure.log` | `fb3b341d5a949380784a35c565004c01bd9db4c4a34ac5549e5fe1bdd430ba59` |
| `host.json` | `0c9ee627f94d34d95e298e505bf779158b620f43b76fd71174d693405a2115d2` |
| `lfu.json` | `0386e329f77c9ec45547d8bffa8c6f79c06f5f2cbc6a22577dc9159d77be3faa` |
| `lru.json` | `184e579bef8a4b60c1ac435440b4bd65c83bc6115b0ce607a6ee87adf03f44bd` |
| `roofline.json` | `1558728444936ed6c0713ec4b542f012b508456a64716c4455f5ea530c941968` |
| `transition.json` | `cedd664811e869581bd5e444b5db58b3a7dd9f29e0cd294ad3af98d86dc0d684` |
| `union.json` | `42746652abf698cb4b1178bbdfab850aa3482e25c76d4a0c6faec6ec5ce8629a` |

## Git result and next gate

Dedicated local branch `research/tesy-n0-foundation-20260923`; root history,
no submodules, origin URL set, upstream absent. Remote remained empty at last
check; connector branch creation returned 409 and parentless commit creation
is unavailable in the action schema. No push or PR is claimed. Complete local
history is delivered as a Git bundle, with source and validation archives.

Next gate: real native routing collector and byte-span validation against the
pinned stock qwen3moe backend, then demand-only quantized integration and exactness.
No larger-model performance admission or novelty declaration is issued by N0.

## Publication reconciliation update

After the bundle reproduction, a fresh GitHub read found the remote initialized.
The observed research base is 41661533bfd0e91251f6840a4b8dc3a2d528d27f, tree
1a03d2098bd4ee4673b1e78dc418f09025c6f065. The new remote branch
research/tesy-causal-residency-20260923 was created successfully from it.
The empty-repo failure above is preserved as history, not used to claim an
ongoing blocker. Existing AGENTS.md and scientific documents are retained.
The README is reconciled with actual delivered command syntax. Native/Python
implementation and tests are unchanged by this documentation reconciliation.

A clean clone of the self-contained pre-publication bundle reproduced all
107 Python tests (6.03 s), the native Release build and 1/1 CTest. That is a
second synthetic software reproduction, not another model/host campaign.
Final API publication/readback identities belong in the delivery receipt.
