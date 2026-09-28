# C48 CPU buffer identification boundary

- **Objective:** resolve the C47 source assertion and test the parked-pair mechanism at a new identity. This unit only asks whether OFF, ON, and fresh-process ON have bitwise identical selected full logits and 250 captured states. No timing claim is permitted before same-pin canonical references.
- **Base:** investigation `2ca6382`; isolated backend C47 `6a2c6c1` plus C48 fix `0bc5c75`. The original backend remains an independent control. Source patch: `research/patches/C48-host-buffer-fix.patch`.
- **Prior evidence:** C46 found 71,260 active of 708,540 prefill wave pair slots; its diagnostic ranges cannot be treated as removable time. C47 OFF captured successfully. C47 first ON aborted at `GGML_ASSERT(device)` before prefill because the stock CPU buffer type has a null device; this remains a FAIL. C47 fresh ON, references, and timing were NOT_RUN.
- **Hypothesis:** testing host accessibility of the streamed weight cache identifies the CPU execution path without dereferencing a null device. The C47 parked-pair `+0` contract then remains bitwise equal to OFF in selected outputs.
- **Alternative:** an incorrect buffer classification, output dependency, lifetime change, or numeric implementation difference causes an assertion or same-profile mismatch.
- **Prospective gate:** parser/model-free tests, clean source/build and model identity, E18 preflight, 300-second thermal idle before each arm, OFF→ON→fresh ON, full logits and six core stages for 250 states, 2 explicit masked states, active-byte witnesses. Stop at the first failure, preserve it, and use a new identity for any diagnosis. CPU 95 °C warns; 100 °C or explicit thermal limit stops. No new power policy.
- **Evidence class now:** source fix and parser tests only. Full-model, references, timing, quality, and M4 are NOT_RUN for C48 until receipts exist.
- **Decision path:** a boundary PASS permits a separately frozen same-pin canonical reference unit. Failure closes C48. No C47 receipt is reused as a C48 PASS.

## Result and decision

- Measurement commit `e091b7134a94314d199278dc4d374e740e26ac1d`; OFF `c48-g2-off01` completed in 71.150 s and ON `c48-g2-on01` completed in 58.063 s. Both individual capture/resource gates passed, with zero swap and OOM. These instrumented durations are diagnostic and cannot be promoted as speedup.
- The first OFF/ON mismatch is `prefill0`, layer 0, `ffn_moe_out`, token 4, feature 0: 0.4479004741 versus 0.0882117599. The preceding captured states in that layer matched. In total, 1442/1500 core rows and all five complete logits differed. The ON capture had 80,800 parked sentinels. The thermal peaks were below the guards; the failure is numerical, not thermal.
- **FAIL_SAME_PROFILE_FIDELITY.** The fresh ON repetition, canonical resident references and timing were NOT_RUN by the stop rule. The C47 assertion remains a separate FAIL. The C48 correction resolved that assertion but did not validate the mechanism.
- **Alternative now favored:** zeroing parked pairs inside the existing CPU MMID pipeline changes active wave results after the first mixed active/parked token. The exact kernel or graph dependency remains unknown. A local source diagnosis may use C48 raw, but any repaired full-model mechanism needs a new identity and fresh reference gates.
- **Next discriminating gate:** exact-prefix/session server pair for M3, because existing C19/C23/C37 evidence already shows reuse potential while full session utility remains open. This pivots mechanism rather than retrying the failed C48 allocation. M4 remains NOT_RUN.
