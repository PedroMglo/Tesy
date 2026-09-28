# C43 wave critical-path diagnostic

- New prospective identity after C42 8K retrieval. Original control → C15 plain → C15 profiled, each conditional on previous receipt, with same 513-ID synthetic prompt and E18 guards. C15 timings diagnostic only.
- `c43-control-cold513` PASS_DIAGNOSTIC_BRIDGE at measurement commit `d5a23e30aed8eea6dd65445aae7c57a2c4fa8109`: official 513 IDs/SHA `bc41ccff…`, four-token output, prefill 79.520 s, max CPU95.125 C/GPU59 C/NVMe43.85 C, GPU5752 MiB, swap/OOM zero. Own model process and port closed. C15 plain/profile NOT_RUN at this checkpoint.
