# C31 finite cache-miss reproduction

- Objective: capture the cache_n35 path seen once in C29, after C30's two source-logged hits. Original backend/binary/model/profile/inputs remain the same; diagnostic environment `LLAMA_SERVER_SLOTS_DEBUG=1`, verbosity4 is frozen. All prior FAILs and two C30 hits remain separate.
- Hypotheses: actual slot/input token LCP differs early; or a long LCP is reduced by SWA/checkpoint availability. The source's old/new token boundary and fallback trace distinguish these. Incomplete logs cannot be interpreted as a cause.
- Maximum three new fresh processes, each admitted after a 300 s thermal window. Stop on the first actionable miss; later runs require earlier cache gates PASS. Three hits end with INCOMPLETE_DIAGNOSTIC and a pivot to a different serving/cache mechanism or source instrumentation, without opportunistic repetition. Instrumented times never promote speed.
- M3 partial, M4 NOT_RUN, C15 source-only, default unchanged. This is an engineering diagnosis, not a claim of cache reliability or miss probability.
