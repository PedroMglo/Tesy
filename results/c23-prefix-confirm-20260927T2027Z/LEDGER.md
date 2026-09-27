# C23 independent exact-prefix confirmation

- Base runner commit `010d045`, preflight import repair `3a502ce31911fe28885fb7ff5930bbc21f274faf` before any C23 model output. First preflight call failed model-free with a wrong import; no run/receipt was created. After repair, 41 focused tests PASS and physical preflight `READY_FOR_IDLE_ADMISSION`.
- Parent C22 screen GO: two paired second-request gains 80.539%/80.704% on the same frozen synthetic 513/641-ID input. Those times do not enter C23 confirmation.
- Six new runs frozen: OFF→ON; ON→OFF; OFF→ON, fresh process per arm. Same P12 8K server profile, model/backend/binary/library/input, 4-token caps, CPU95 warning/CPU100 stop, E18 zero swap, GPU80/NVMe70 and 300 s matched idle policy as C22. Only second-request cache_prompt varies.
- Confirm threshold frozen before outputs: median of three paired second-request gains ≥20%, all positive; median first-cold gain ≥−5%; all output/cache/resource/telemetry gates PASS. Three pairs are descriptive, not tail or sustained evidence.
- C15 remains source-only; M3 partial and M4 NOT_RUN. Default unchanged. Runs NOT_RUN at freeze.
- `c23-p1-off` PASS at measurement commit `c25c636132287f326b860e65f4ce7019ccbc2d72`: start CPU 45.875 C after 300 s idle; 513+4 81.052 s, 641+4 95.313 s; cache_n 0/0; CPU max 95.125 C, GPU total 5752 MiB, swap 0. Raw SHA `064d67a875ec1a8dad82abc0fc2fcd829a166e76f4cc848e5bffe66d49c3ac1a`. No paired gain until ON completes.
