# C84 expert-demand trace diagnostic

- Backend source `5a1f4c5d9ed06021d58813ffb41792e83f337513` from C75 `27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5`; Tesy source freeze `8760850d6f8ca4d43af772891a90337697299005`. Patch and hashes are in `protocol.json` and `model-free-tests.json`.
- Added a bounded, opt-in trace for distinct expert demand, slot status, reserve/evict, preload, load and wait spans. It buffers at most 300000 events and writes once at clean shutdown; overflow or incomplete output is a failed trace.
- Model-free: CUDA arch89 server build and `--help` passed. Five parser controls passed. A tiny CPU streaming callback produced 44 demands, 40 loads, 8 evictions and 10 waits; C84 and C75 returned the same slot hash `4342555887178113839`. Existing trace path was rejected without replacement.
- Trace bytes are logical expert payload; tagged I/O and independent controller counters would be separate. Instrumented time is diagnostic. No 120B, server request, CUDA callback or L2 benefit is claimed.
- Next: explicit client request/phase monotonic markers and 8K session numeric bridge after fresh capacity admission; then a bounded warm153 trace if the bridge passes. C48/C61/C66/C78 failures and C79/C82 non-admissions stay unchanged. No default or remote write.
