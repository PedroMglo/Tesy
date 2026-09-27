# C7 P12 minimum-forward capacity result

Objective and measurement identity: a single 113-ID P12 prefill, with no teacher forcing, under `results/c7-20260927T1130Z/capacity-protocol.json`; measurement commit `0e032d1b8a2ec9c2bcfab654e888cd0b68ffdeea`, tree `bfc7f3010dae95196c705c162551bf624d1dbe34`. This was a capacity diagnostic, not performance screening. Raw run `c7-cap-p12-forward01` is referenced by hash in `capacity-summary.json`.

The run completed 113 IDs and one finite 201088-F32 logit row. The repaired resource gate accepted 74 samples. Measured peaks: GPU total 5670 MiB, RSS 13,023,498,240 B, cgroup 12,855,840,768 B; swap and OOM events stayed zero. The model stat and mapped backend libraries matched the freeze. P12 therefore met the prospective forward reservation of GPU <=6500 MiB, RSS <=16 GiB, cgroup <=16.5 GiB for this one short prefill. The 40.86 s prefill completion is diagnostic and excluded from paired timing.

Decision: capacity admitted for the next bounded gate. The alternative that init-only understated residency was partly true: CPU memory rose materially during forward, but remained within the specified reserve. Long contexts, repeated decode, numeric fidelity, 496/1522 timing, server and quality are NOT_RUN. Next test: freeze the G2 189-ID call plan and observer/reference source, then compare P12 observer OFF/ON and resident layers under E18.
