# C19 P12 exact-prefix mechanism retest

- New identity after C18; original C13 CPU95 FAIL preserved. Same synthetic C13 513-ID first prompt and 641-ID incremental prompt, P12 8K original backend, CPU100 prospective guard, E18 zero swap.
- C18 completed four cold513 arms; this gate measures whether server `cache_n` reports at least 450 actual common prefix IDs on the second request. It is a mechanism/resource diagnostic, not M3 qualification.
- 10 model-free focused tests passed. New preflight passed; physical run pending. C15 remains source-only.
- `c19-g1-prefix-on` PASS_MECHANISM at `caa010b9a157c133eedaabec7c927ea83c64c2a5`: first 513+4 80.601 s, second 641+4 18.499 s, common/cache_n 510/510, second backend prompt_n 131. CPU max 95.125 C, no mitigation/guard, raw SHA `219a11e21844785b23a43edcad60e4b1132bc063c2f9fcfa9d22a1eacfddc53c`. C13 CPU95 FAIL untouched. Next C20 paired OFF/ON control; M3 partial only.
