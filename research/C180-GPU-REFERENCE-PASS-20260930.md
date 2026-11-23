# C180 — canonical FFN selected scope qualified

MEDIDO_NO_TARGET: all GPU-side layers25–35 and CPU0 regression passed five rows each: canonical routing IDs, weights and FFN outputs bitwise, all finite. Combined with C179 layer24 and unchanged/revalidated C169 CPU1–23, this closes all36 canonical FFNs for the C16632+4 captures. Old C169 mismatch remains preserved; matched native backend/fused reduction fixes the independent reference without any epsilon.

CPU experts remain CPU across all layers; layers25–35 router/reduction are CUDA0, layer24 routerCPU/reductionCUDA0. Dummy storage location alone was never used as execution evidence. Source-plan detectors and operator controls passed, but this is selected activations/schedules rather than universal attention/KV or warm153 qualification.

Next: short natural repeated chat to test retained exact prefix. The server path reuses c2 with prospective FILE_PAGING end accounting; old streaming cap semantics remain. Added tests cover high/scope admission, allowed reclaim, OOM/swap rejection and real child/monitor/receipt with mocked transport, plus four-arm prelaunch negatives. Directed suites only; full suite NOT_RUN. A harmless HTTP smoke precedes weights on the real server entrypoint.
