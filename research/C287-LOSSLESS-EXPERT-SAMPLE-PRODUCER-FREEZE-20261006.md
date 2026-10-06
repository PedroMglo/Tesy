# C287 — lossless sample producer freeze

Before weights read:64 experts, eight predetermined CPU/GPU layers, expert IDs0/17/34/51/68/85/102/119, six GGUF components each. Original MXFP4 inline scales preserved, biases retained in pack even though native demand loading already has biases resident. No target forward or fullpack authorized here.

First run synthetic direct-reader faults (same btrfs filesystem32KiB); second run pack from original qualified C211 canonical reader. Pack exclusive-create O_DIRECT, bounded staging16MiB, aligned zero padding, component SHA256 and whole write-stream SHA256. Readback qualification deliberately pending until service probes.

Own60s inventories/freshness<=3s, common2GiB/high=max/swap0/guard1.5GiB, total375s physical envelope, raw2MiB, samplepack<2GiB private/persistent. Source/binary/libs/OpenSSL/model-stat chain and metadata are pinned in protocol. No new whole-model hash claim. Source and tests are instrument progress, not measured useful speedup.

Next protocol freezes actual readonly pack/index identity and A-B-B-A full CPU/CUDA bytes-ready service with four workers and common request/barrier schedule. Investment gates: both service pairs positive, combined serial service median>=15%, optimistic critical scenario>=10% decode in an identified case, engineering<=12h. Projection is conditioned and no formal server bound; requires isolated integration canary if admitted. All failed attempts remain. LOCAL_ONLY.
