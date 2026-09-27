# C20 P12 prefix OFF/ON screening

- Base C19 `30dfb1d`; input/server/backend/guards frozen, only cache_prompt on the second request changes. Pairs OFF→ON; ON→OFF, fresh server processes and matched thermal starts.
- Prospective screen: median paired second-request gain >=20%, both positive, median first-cold gain >=-5%, cache OFF 0/ON >=450 IDs, same returned messages and valid resources. Three new confirmation pairs follow only if screen passes.
- Ten focused model-free tests and physical preflight passed. Runs pending; C15 source-only, M3 partial, M4 NOT_RUN.
