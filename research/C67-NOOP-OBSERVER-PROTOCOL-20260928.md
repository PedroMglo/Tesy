# C67 no-op observer discriminant

- Objective/base: determine whether merely registering `cb_eval` reproduces the C66 layer25 invalid routed ID. Base Tesy `e486028852e7546b1425a347685cc754e883e9b0`, C66 backend `1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22`. C48/C61/C66 failures remain unchanged.
- Alternative: callback registration changes scheduling enough to expose the failure, versus tensor reads/checks performed by C60 capture. A passing single no-op run weakens the first explanation but does not prove a root cause.
- One intervention: `tools/c67_noop_observer_probe.cpp` is the C7 plain probe with only a callback returning false and two diagnostic labels changed. It reads or writes no tensor. Model, P12/ub32/slots32/n_ctx4096/no preload, inputs, external calls and output masks match C66 plain. The full 33-logit payload must equal C66 plain bitwise if the arm completes.
- Model-free: C66 CUDA backend and C67 probe compiled; source delta was inspected; protocol builder reproduced from C66 inventory and pinned plain output hash; four focused Python tests passed. This does not qualify physical behavior.
- Gate: new 60-second inventory and committed freeze, one E18 zero-swap bounded process, first failure ends unit. Invalid-ID abort, full-logit mismatch, resource/evidence failure and pass are separate outcomes. No timing/quality promotion.
