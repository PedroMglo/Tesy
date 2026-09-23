# Reference host identity and first bring-up runner

Date: 2026-09-23
Status: prospective DEVELOPMENT protocol

Tesy's supplied reference hardware is now encoded in
`configs/reference-host.json`:

- Linux;
- AMD Ryzen AI 9 HX 370;
- 24 logical CPUs;
- one NVIDIA GeForce RTX 4060 Laptop GPU;
- approximately 8 GiB VRAM;
- approximately 32 GiB RAM.

Ranges are used for RAM/VRAM because OS/firmware reporting is not an exact
marketing-capacity identity.

Driver version, CUDA toolkit, available memory, storage mounts, competing
processes and temperature are intentionally **not** frozen in this hardware
identity profile. They are campaign state and must be recorded separately.

## Check

```bash
tesy doctor --reference-profile configs/reference-host.json
```

A PASS only proves the observed host matches the intended physical hardware
class. It does not prove the machine is idle or ready for timing.

## Bring-up pipeline

After installing the locked gpt-oss-20b model:

```bash
bash scripts/run_reference_bringup.sh \
  ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  results/bringup-20260923TXXXXXX
```

The output root must not exist.

The runner performs:
1. clean Tesy worktree check;
2. live reference-host identity check;
3. pinned stock llama.cpp bootstrap/build;
4. native tracer build;
5. pinned gguf-py install in the active environment;
6. stock model smoke;
7. trace OFF/ON token-equality diagnostic;
8. GGUF expert payload inventory.

It deliberately stops before choosing byte-cache capacities or a custom Tesy
cache. Those decisions must use the observed inventory/resource envelope and
be frozen prospectively.

A final
`PASS_DIAGNOSTIC_REFERENCE_BRINGUP_PIPELINE`
is not a performance PASS, not a chat-quality PASS and not a Tesy speedup.
