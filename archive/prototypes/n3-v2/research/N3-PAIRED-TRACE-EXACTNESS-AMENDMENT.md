# N3 amendment — paired trace exactness output

Date: 2026-09-23
Status: prospective implementation correction
Base before change: `72c31eb26960a153520cbf10f4bc3e1bd4e2f621`

## Finding

The paired trace script already required `--tokens-out` from the native tracer and compared trace-disabled vs trace-enabled token files, but the tracer parsed that option without writing the file.

Therefore the documented paired exactness check was not executable even though the native tracer itself compiled successfully.

This is an implementation defect, not a model result.

## Correction

The tracer now writes a small no-replace JSON artefact:

```json
{"schema":"tesy.generated_tokens.v1","tokens":[...]}
```

The output contains generated token IDs only. It is deterministic for an otherwise identical greedy run and is suitable for byte-for-byte comparison.

The initial paired routing diagnostic also adds `--raw-prompt` to both arms. This avoids using the low-level `llama_chat_apply_template` helper as a substitute for the stock llama.cpp Jinja/Harmony conversation path.

This choice deliberately narrows the first trace question to:

> Does enabling the passive `ffn_moe_topk` callback change the generated greedy token trajectory under the same raw-tokenized input?

It does **not** qualify gpt-oss chat formatting. Stock conversational bring-up remains a separate backend smoke/server task using the backend's actual supported template path.

## Gate on physical host

Run:

```bash
bash scripts/compare_trace_exactness.sh MODEL.gguf results/trace-exact-<campaign>
```

Required outcome before traces are used scientifically:

```text
PASS_DIAGNOSTIC_TRACE_TOKEN_EQUALITY
```

A mismatch or missing token file is a retained failure for that campaign. Do not retry the same campaign identity.

## Claim boundary

No model was opened by this amendment.
No GPU result is claimed.
CI compilation validates source/API compatibility only.
Token equality is still NOT_RUN_MODEL_REQUIRED until executed on the admitted model.
