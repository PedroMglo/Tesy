# n-cpu-moe sweep stream-token parser correction

Date: 2026-09-23
Classification: REPRODUCED_INSTRUMENTATION_DIAGNOSIS
Affected campaign: `results/n-cpu-moe-sweep-20260923T214340Z`
Decision: preserve FAIL and retry with a new campaign identity

## Observed failure

Tesy's SSE client stopped on the first sweep observation:

```text
ServerClientError:
streamed token count does not match server predicted_n: 67 != 64
```

The server itself reported `predicted_n = 64`.

## Source diagnosis

At the pinned llama.cpp commit
`4e416ee7308dd6b581796f1a6241276cd5982691`,
prompt progress is sent with:

```cpp
send_partial_response(slot, {}, true);
```

In `server_context::send_partial_response`, an `is_progress` result still
passes through the non-`is_begin` branch and populates:

```cpp
res->tokens = { tkn.tok };
```

The non-OAI serializer then emits both `tokens` and `prompt_progress`.
Therefore a progress event can carry a token placeholder even though it is not
a generated-token event.

Three such progress events explain the observed 67 = 64 + 3 count.

## Correction

`tesy.server_client._event_token_ids` ignores a `tokens` field only when
the same event contains `prompt_progress`.

The exact trajectory contract remains:
- 64 generated IDs per observation;
- `len(generated_token_ids) == predicted_n`;
- all 14 observations must have identical token-ID lists.

No threshold or target semantics were relaxed.

## Retry boundary

Do not reuse `results/n-cpu-moe-sweep-20260923T214340Z`.

Run a new campaign only after model-free tests/CI pass. If the new run still
produces a token-count mismatch, preserve it and stop again.
