# C69 targeted wave boundary

- Measurement: dd77bee39198bb8c28ef0e0bb27c2f5a813e2b81; backend: 1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22.
- Command: `PYTHONPATH=tools python3 tools/c69_wave_on_boundary.py run results/c69-wave-on-boundary-20260928T1641Z --measurement-commit dd77bee39198bb8c28ef0e0bb27c2f5a813e2b81`.
- Run c69-p12-wave-on01 passed targeted P12 layer0/prefill0 bitwise active boundary and five full logits against C68 OFF. ON had 1152 skipped-pair sentinels; no invalid ID. CPU max 65 C, GPU 52 C, VRAM total 5690 MiB, swap 0.
- C48/C61/C66 failures remain. Other layers, canonical references, timing and quality are NOT_RUN. Next gate: full-layer same-profile fidelity.
