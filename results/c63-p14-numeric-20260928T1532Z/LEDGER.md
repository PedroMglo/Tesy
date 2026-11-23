# C63 boundary ledger

- Measurement commit `d5cbb2a3f43dd137ea0d9a84fc8f9b92c675ff89`; C35 backend P14, 8K context, preload ON, E18 zero swap.
- `c63-p14-off01`, `c63-p14-on01`, `c63-p14-off02`: all complete. OFF 33 full logits rows repeat bitwise; ON five selected logits match. Capture has 250 numerical states, 2 masked states, 1518 byte/lifetime witness rows.
- Loader observed CPU0–22, CUDA23–35 and output CUDA. GPU peaks 6680/6690/6680 MiB; CPU peaks 91.625/91.375/91.5 C. No guard/swap/OOM stop.
- Canonical resident reference and timing NOT_RUN. C48/C61 failures unchanged. Next: witness layers 23/24/22/25/0/35, then remaining layers. Raw local only; no remote write.
