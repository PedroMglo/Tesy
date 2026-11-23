# C128 — prospective slots40 nominal153 screen

Objective: test whether added exact expert residency and changed wave capacity
improve incremental decode under the same operational C75 server profile.
Alternative: the LFU pool already retains useful experts; larger pools add
memory/work without shortening the critical path. C127 established only short
numeric and forward admission, not performance.

The two arms use the **same original C75 binary and mapped libraries**, wave
flag ON, P12, ctx8192 and ubatch32. The control has 32 expert slots per
layer and the candidate 40. This explicitly defines two numeric profiles.
All other C121 nominal153 settings, official tokenizer/template, medium,
sampling, real assistant history, preload, full SWA, F16 unified/offloaded KV,
E18/swap0 and per-arm 60 s start inventory are unchanged. The frozen configs
and protocol hashes are the authority. The workload is the C121/C124 fixture:
the second turn is nominal128 words and previously evaluated as 153 new IDs
with 2044 reused; actual IDs and outputs will be reported, not forced.

Four new processes, in order control/candidate/candidate/control, form two
pairs. Primary: incremental warm decode duration for equal official prompt
IDs and exactly equal generated messages/token counts. Screen GO requires a
median paired gain at least 8%, both pairs positive, and median protections
at least −5% for warm first final, warm prefill, cold decode, cold first final
and cold prefill. All answer, prefix, identity, inventory and resource gates
must pass. Divergent generation is operational evidence but cannot support
the equal-work decode screen. Do not silently adjust gates after observation.

Operational warm start requires valid sensors/AC/performance and each arm's
fresh inventory through actual Popen. It does not require 3/3/2 °C matching
or deliberate cooling. Temperatures, clocks, power and pressure remain
observations and potential confounders. Page cache is uncontrolled; expert
I/O uses the frozen direct-I/O configuration. Timeout600 s per process,
450 s per request. Reserve four times 660 s plus600 s closure and7200 s for
qualification before starting. Raw new in this epoch stays under20 GiB.

Model-free gate: C120/C118 strong gate tests, new wrapper freeze/frozen
consistency, config diff exactly slots32/40 with backend/libs/flag constant,
negative control for each protected metric and output divergence in analyzer.
Run a harmless scope/entrypoint smoke if the wrapper changes launcher logic;
this wrapper delegates launch/inventory to the already proven C120 path.

No default/main/remote writes. Historical C100/C117 failures and C124
confirmation remain authoritative in their own scopes. M4 is not declared
by a slots40 screen.
