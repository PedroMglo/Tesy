# C42 CPU frequency monitor repair

- Objective: distinguish one transient impossible `cpuinfo_avg_freq` read from a persistent telemetry fault, after C41b stopped at policy19=21786195 kHz. Base `4c196d4` and C41b failure remain immutable.
- Change: permit one immediate reread when first value is zero or >=10000000 kHz. A valid second value is used and both values are recorded; another invalid value fails. Negative or non-integer first values remain failures. High rereads have their own receipt field and summary count, separate from zero rereads.
- Evidence class: source/model-free. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest tools.test_c18_cpu_telemetry tools.test_c40_parent_death tools.test_c3_terminal_sample` passed 7 tests. A live idle capture returned 24 policies and zero rereads. The high-then-valid and persistent-high mutants discriminate.
- Alternative: C41b could reflect a persistent kernel/sysfs fault. The prospective C42 run will stop if the immediate reread is invalid; this repair cannot requalify C41b or prove an 8K result.
- Decision: freeze this monitor source in a new C42 campaign with fresh preflight and unchanged model/workload/guards. C15 remains NOT_RUN; no default change.
