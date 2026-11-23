# C65b P12/P14 screen

- Objective/base: test P14 placement against P12 under frozen C35 backend and E18. Base P14 same-profile evidence: C63 observer and C64 36 canonical routed FFN loads. Code `ad05cac`; measurement `630792e137cde86ba25cf31c4c3992443968465d`.
- Evidence class: `MEDIDO_NO_TARGET` for eight paired probe arms; `SOURCE_AUDITED` for the call plan. Raw hashes, per-run receipts and resources: `results/c65b-p12-p14-screen-20260928T1553Z/manifest.json` and `runs.jsonl`.
- Alternative: added GPU placement may fail to reduce total work or perturb decode. The 113-token result was diagnostic; medium 496+32 was the prospective investment gate. The metric was completed prefill plus 32 teacher-forced steps, gain computed per pair with each P12 denominator.
- Result: medium gains 6.673% and 2.074%, median 4.374% against required 5%; `NO_GO_SCREEN496`. Short gains 2.133% and 7.891%, median 5.012%, exploratory. Repeated full 33-row logits were bitwise within profile. Cross-profile logits differ while the observed greedy top1 matched; no sampling or quality equivalence follows.
- Resources: all eight arms passed E18, zero swap/OOM/guard; max CPU 92.5 °C, GPU 60 °C, total GPU 6680 MiB. The screen cost 716.165 s of bounded process elapsed plus 60 s inventory; page cache not controlled.
- Limitations/NOT_RUN: no P14 medium confirmation, no 1522 check, server TTFT/final response, functional tasks or independent attention/KV reference. P14 is not promoted. C48 and C61 remain failures; C65 earlier freeze had no inference.
- Next discriminant: diagnose the C61 invalid expert ID in the wave-planning source/model-free path before another C57 physical attempt; compare with bounded L2 trace evidence before selecting a physical mechanism.
