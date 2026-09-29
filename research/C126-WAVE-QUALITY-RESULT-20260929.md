# C126 — C75 preserved the C40 twelve-task result

**Decision: `PASS_QUALITY_12_OF_12` (MEDIDO_NO_TARGET, tested scope).** The
original C75 waves backend, P12/slots32, completed all twelve frozen C40
code, SQL/data and planning tasks with `finish_reason=stop`. All twelve
original validators passed. Official input token arrays and final assistant
messages were exactly equal to C40 P12 for every task. This is a stronger
functional observation than matching token counts; it remains a twelve-task
synthetic fixture, not broad quality equivalence.

Source commit: `1627c874b82b16a8db3bc78106bf2d0f121f7bf7`.
Measurement/freeze commit: `784f387e8cf775b9bf863cf04f9047d4fa6fa6e4`.
Backend: C75 `27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5`, with
`TESY_CPU_WAVE_SKIP_PARKED=1`; original model and quantization. The 57 server
arguments matched C40 P12 except for the binary path. The resource policy,
binary and mapped library hashes, model stat, run scope, prompt IDs and
validator hashes are in the frozen protocol and receipt under
`results/c126-wave-quality-20260929T1610Z/`.

The server elapsed 2403.864 s; the unique live envelope including the
per-arm inventory and grading was 2466.621 s. Maxima: cgroup 13,131,096,064
bytes, GPU use 5758 MiB, CPU 72.75 °C, GPU 55 °C, NVMe Composite 59.85 °C;
zero workload swap, OOM, resource stops and incomplete responses. The raw
server JSON SHA256 is
`bd9e34e36193811b3b880e3f3912253ea70464ede3c347f59de2162bbe808eda`.
The manifest records hashes for every other raw and compact file.

The C126 median first final was 131.85 s versus 140.10 s in historical C40.
This is descriptive across different days and regimes; it is not a paired
speedup claim. C124 remains the admitted nominal153 performance confirmation.
C100 `NO_GO_CONFIRM` and C117 `FAIL_RESOURCES_OR_EVIDENCE` remain in force
for their contracts. M3 retains its prior spaced twenty-request scope; diverse
assistant-history and active sustained use are NOT_RUN. M4 is NOT_DEMONSTRATED.

Model-free checks: C40 gold/mutant validator self-test PASS, C126 syntax and
protocol reconstruction PASS, exact C40/C126 12-array token input equality
PASS. The first sandboxed `systemd-run` invocation was denied access to the
user bus before creating any model process; the authorized unsandboxed
invocation used the same frozen measurement commit. It is an operator attempt,
not a thermal or model FAIL.

Budget checkpoint: the conservative physical remaining lower bound after
C126 is 6.056 h; wall remaining at the checkpoint is 8.644 h. Raw C126 is
3,479,408 bytes; the epoch total remains under 20 GiB. See
`epoch-checkpoint.json` for the exact charge method and prior checkpoint hash.

Next discriminating gate: C127 P12/slots40, a separate numeric profile. The
C123 trace has 302 of 1509 decode misses after an in-trace eviction with at
most eight distinct subsequent reservations in that layer. It does not
reconstruct the hidden LFU state of the prior request, so it is a heuristic,
not a predicted speedup. Static pool growth is 2.462 GiB CPU and 1109.4 MiB
GPU. Before timing: fresh admission, allocation and short forward, slots40
OFF/ON boundary equality, resident canonical reference of all 36 FFN layers
and full-logit checks. If faithful and within guards, screen slots32/40 on
fresh nominal153 pairs, protecting decode, prefill and quality.
