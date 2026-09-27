# C20 P12 prefix OFF/ON screening

- Base C19 `30dfb1d`; input/server/backend/guards frozen, only cache_prompt on the second request changes. Pairs OFF→ON; ON→OFF, fresh server processes and matched thermal starts.
- Prospective screen: median paired second-request gain >=20%, both positive, median first-cold gain >=-5%, cache OFF 0/ON >=450 IDs, same returned messages and valid resources. Three new confirmation pairs follow only if screen passes.
- Ten focused model-free tests and physical preflight passed. Runs pending; C15 source-only, M3 partial, M4 NOT_RUN.
- `c20-p1-off` PASS at `dae7261be9b7f66fbfd0485e9ea6e130d6745f05`: first 80.263 s, second 93.931 s, cache_n 0/0, CPU max 95.125 C, no mitigation/guard, raw SHA `4b64df9e721dfd7e20866656d3ac19163797a87bf9ed79072b596ba2f4db384a`.
