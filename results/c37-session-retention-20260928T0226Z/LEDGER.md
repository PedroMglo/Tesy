# C37 8K spaced session retention

- Prospective one-process, 20-request synthetic prefix-extension test with 180-second idle gaps and fixed template date. C36c 4096 prefix PASS is parent. No C37 physical run yet.

- C37 run `c37-spaced20-prefix` PASS: 20 complete synthetic requests in 4322.635 s; 19/19 adjacent cache gates; E18 zero swap/OOM; CPU max95.125 C warning, GPU62 C, NVMe51.85 C. First/last incremental medians 30.701/33.101 s; first/last decode medians 4.736/4.396 tok/s. M3 partial, M4 NOT_RUN, C15 model NOT_RUN. Measurement commit `c19462e1bbccfeb09d1683483adccdfe5781a722`; see decision/manifest for raw SHA and limits.
