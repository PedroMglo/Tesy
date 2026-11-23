# C65b P12/P14 timing screen

- Code `ad05cac`; frozen measurement `630792e137cde86ba25cf31c4c3992443968465d`. Model and C35 backend unchanged; P12/P14 differ only in `n_gpu_layers`. E18, zero workload swap, 8K full-SWA/F16 KV, ub32, slots32, preload ON.
- `python3 tools/c65_timing_run.py run results/c65b-p12-p14-screen-20260928T1553Z --measurement-commit 630792e137cde86ba25cf31c4c3992443968465d` completed eight fresh-process arms in the frozen order. All bounded runs passed identity, mapped libraries, output shape/finite, loader placement and resources. All 33 logits rows repeated bitwise within each profile and case.
- Short 113+32 teacher-forced pairs: T_work gains 2.13%, 7.89%; median 5.01%. Medium 496+32 pairs: 6.67%, 2.07%; median 4.37%, below the prospective 5% screen. Medium `NO_GO_SCREEN496`; no confirmation or server claim. P14 short signal remains exploratory.
- Max CPU 92.5 °C, GPU 60 °C, GPU total 6680 MiB; zero workload swap/OOM/guard stop. Raw 215053177 B/80 local files, SHA in `manifest.json`; not committed. Page cache uncontrolled.
- C48 and C61 FAILs unchanged. M3 retains C52b tested mechanics scope; M4 not met. Next: diagnose C61 invalid expert ID model-free and evaluate whether wave work or bounded residence has the stronger discriminant.
