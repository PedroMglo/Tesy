# C115 ledger

- Frozen model-free calculation from hash-bound C114/C111/C108 evidence; targets 10 s first final and 6 tok/s unchanged.
- Analysis PASS: first final25.115 s, measured prompt12.353 s; zero-prompt fixed-rest scenario12.762 s, still2.762 s above target10. Observed3.571 tok/s requires40.48% less per-token time to reach6 tok/s. Raw-hash mutation rejected. This is conditional model-free inference from one ON request, not a causal A/B gain. No model or remote publication.
