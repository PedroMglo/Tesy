# C134 — 8K boundary interrupted by control plane

C134 was frozen at `ffbf139503a304510360afed0c9d4812228d6910` and launched under E18/zero swap. The 60-second start inventory and model launch completed. During the 7936-token prefill, the execution daemon restarted and interrupted the tool session. The own server stopped; stderr shows cancellation after 2621 prompt tokens. There is no complete response, raw JSON or terminal receipt. Status: `INTERRUPTED_BY_CONTROL_PLANE`, not a boundary PASS and not a thermal failure.

Local launch, inventory, official tokenization, samples and stderr are preserved with SHA256 values in `interruption.json`. The last sample is at 82.62 s after server launch. This partial observation cannot qualify full-context capacity or latency. C42's original slots32 result remains unchanged.

Conservatively charge 240 s for this live attempt. Before a new physical identity, exercise a detached user service with a small model-free process and verify its cgroup cap and zero-swap setting. A new C134b may reuse the same prospective workload/gates if budget admits; C134 remains interrupted.
