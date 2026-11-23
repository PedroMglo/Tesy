# C287 — producer and direct reader qualified

MEDIDO_NO_TARGET / REPRODUZIDO_MODEL_FREE: actual same-filesystem synthetic32KiB direct tests passed including unaligned logical offsets, reuse, EINTR, short/failed read, no buffered fallback, EOF and overflow. Native mappings and selective runtime observed, no guard/telemetry/OOM/swap failure.

Frozen64-expert pack created with6canonical components per expert, explicit aligned padding,384component hashes and complete write-stream SHA256. Component readback and CPU/CUDA destination proof remain pending for the service family. Readonly after producer. Original model unchanged. No fullpack, Transformer or performance claim.

Measurement HEAD93eb5f8; physical family124.666596s including two60s inventories, faults and pack generation. The gate test file temporarily received additional pure family-cardinality tests during execution, then was restored to its frozen hash before producer launch; no measured executable/gate/source was changed and that file is not consumed by either process. This limited editorial occurrence is preserved, not used to claim execution of extra tests under the old freeze. Extra tests are separately frozen for C288.

Persistent pack path/index and full raw SHA/size manifest: results/c287-lossless-sample-producer-20261006; pack under epoch/pack, ignored by Git. LOCAL_ONLY. Next: four fresh bounded A-B-B-A service processes with new probe source identity (fd stability and readonly checks outside timing), common requests and native destinations.
