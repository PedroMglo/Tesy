# C22 repaired paired prefix screen

- Objective: measure the C19 exact-prefix mechanism against cache OFF on the same P12 server. Alternative: reuse of 510 IDs does not give a material completion-fenced second-request gain after accounting for warm server and order.
- Base `fcdad67`; measurement commit follows frozen protocol/preflight. The C21 failure was a missing output directory before model launch; its idle and run identity are preserved. Repair adds an output-root existence gate before the five-minute idle window, with a model-free missing-root negative. No backend change.
- Evidence class at freeze: 40 focused model-free PASS; host/model/backend/preflight PASS. Physical timing NOT_RUN. The model full SHA was verified in C20 and C22 checked exact dev/inode/size/mtime/ctime before admission.
- Workload/profile/order/metrics/thresholds/stop conditions are in `results/c22-prefix-pairs-20260927T1937Z/protocol.json`; only the second request's cache flag varies. Two alternating pairs; new three-pair confirmation only on screen GO. Raw/server receipts no-replace. C20/C21 data excluded from gains.
- C21's cool-start band is retained: 300 s continuous CPU/GPU/NVMe <=50/50/45 C, subsequent arms within ±5/5/3 C of first start, max 900 s admission. CPU95 warning/CPU100 stop; E18 zero swap, GPU80/NVMe70 unchanged.
- M3 remains partial mechanism, M4 NOT_RUN, C15 SOURCE_ONLY. Next gate: execute four frozen arms sequentially with no hidden retry.
