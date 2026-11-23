# C71 resident canonical FFN reference

- Frozen commit `c9244c9394ebc56b828f3683ebcca64a257d3959`; remaining-layer measurement commit `437b233245158850c0670786c88bb61e6f230b88`; C66 backend `1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22`.
- Commands: `PYTHONPATH=tools python3 tools/c71_wave_reference_run.py witness results/c71-wave-reference-20260928T1659Z --measurement-commit c9244c9394ebc56b828f3683ebcca64a257d3959`; then `remaining` with commit `437b233245158850c0670786c88bb61e6f230b88`.
- 36 resident layer loads passed: 250 numeric rows bitwise in ordered router IDs, routing weights and FFN output; two masked states. First six witnesses were layers 25–28,24,29.
- C48/C61/C66 FAILs preserved. Independent attention/KV, ON repetition, timing, quality and M4 are NOT_RUN. Next: fresh-process ON repeat.
