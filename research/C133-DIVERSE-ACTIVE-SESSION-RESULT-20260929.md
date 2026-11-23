# C133 — varied active session, functional gate 19/20

C133 is a new attempt after C132 reached its frozen 512-token cap. It used C75 waves ON/slots40, the original GPT-OSS120B GGUF, medium, context8192, E18 and zero workload swap. The 20-task fixture, cap768, schedule and validators were frozen before the measurement at `ff9d1d7ff6d7df99156cc8e33a613b99afbc4ed4`; independent analyzer source is `9ac9295`.

Measured on the target: 20/20 natural completions; session span 4999.6 s (83.3 min); consecutive active block 1846.5 s (30.8 min); request-active sum 1999.1 s, duty fraction 0.400; five measured idle gaps all >=600 s. Maximum official prompt 4853 tokens, below the8192 context and768-token output reserve. Cgroup peak 15,996,751,872 bytes, GPU peak 6885.0 MiB, swap zero, no resource stop.

The frozen content gate passed 19/20. Turn02 omitted the literal project name `Aster`, although it answered the prioritization question. This is `SESSION_QUALITY_OR_DURATION_NO_GO`, not a full diverse-session PASS. Later turns recovered the old constraints under their frozen checks. C52b's older 20-request spaced mechanical PASS remains; C133 adds varied history and an active block, with this functional gap. Restart/KV persistence and general quality remain NOT_RUN.

Raw SHA256 `70975912055a8546a9d93f56472e04b95e0e79f066f94d99e5d3a6160406c35b`; receipt SHA256 `6c5fcc8165bef71eae9494085bafbebd2287c24032bec10b854a148616c86286`; analysis SHA256 `e8ee4eca39a0ba731f5a6e9190db422207621971982ab823b86ce05c933a306d`. Raw remains local. Physical charge for C133: 5068.0 s including inventory/server/cleanup. C132 FAIL, C117 FAIL and C100 NO_GO remain unchanged. M4 remains unmet on the prior nominal153 latency/decode measurements.

Next discriminant: the 7936+256 context boundary for slots40, since slots40 changes memory and the previous C42 boundary only covered slots32.
