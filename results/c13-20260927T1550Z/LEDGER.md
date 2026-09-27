# C13 P12 exact-prefix mechanism ledger

- Freeze one two-request synthetic ON arm (513 then 641 official IDs expected) under E18, original backend P12 preload ON, no paired timing or numerical promotion. First request C11 passed once at CPU95 exactly; this diagnostic may fail thermally.
- `c13-g1-prefix-on`, measurement `bafd99001e739c5baab06b85327dc6c5b6ca69bc`: official tokenizer produced 513/641 IDs with 510 ordered common IDs before output. First 513-ID request hit CPU95.125 C at 74.731 s; watchdog ended scope at 80.197 s, zero completed requests. Peak RSS 13.271 GB, cgroup 13.050 GB, GPU 5746 MiB, zero swap/OOM. Second request and `cache_n` NOT_OBSERVED. FAIL preserved; no retry.
