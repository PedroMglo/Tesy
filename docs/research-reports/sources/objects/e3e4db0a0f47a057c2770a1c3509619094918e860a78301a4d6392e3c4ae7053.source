# Resultado: live reinjection e committed continuation — 2026-09-24

## Decisão e proveniência

**MEDIDO:** `LIVE_MOE_REINJECTION_CONTINUATION_EXACTNESS_GO` na campanha física `results/live-moe-reinjection-continuation-exactness-20260924T201414Z/`. A decisão foi produzida pelo validador Python dos raw metadata e dos oito vectores completos de logits F32, não pelo executável nativo. Não existe root falhado nesta fase.

Branch: `research/live-moe-reinjection-continuation-exactness-20260924`. Measurement commit `31720ce16ecbd2ea9d75e3bf56d65e4ca8427a80`, tree `d213686b14b46b0e4268e944e62e187a8c8fac0d`. Base: branch do PR #30, commit `764cb09ade02d8b0a40deb7628baab613510ab09`. PR #31 draft na Stack #22.

llama.cpp `4e416ee7308dd6b581796f1a6241276cd5982691`. Modelo `gpt-oss-20b-mxfp4.gguf`, 12,109,564,352 bytes, SHA-256 `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`. Prompt `benchmarks/prompts/b0-b1-diagnostic.txt`, SHA-256 `431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6`. Ambos verificados na campanha.

## Autoridade stock e quatro braços

Stock uninterrupted produziu os tokens greedy `2167`, `1309`, `316`. O terceiro token foi definido pelo stock desta campanha, como pré-registado. Cada um dos outros braços usou contexto fresco, confirmou rota `[1, 13, 17, 21]` e weights bitwise no callback, e produziu também `2167`, `1309`, `316`. Cada braço fez exactamente uma reinjection no decode committed de `2167`; não houve rollback desse decode. O token `1309` foi depois decodificado normalmente sobre o estado committed.

| Braço | FFN vs stock: relative max / cosine | FFN bitwise | Pre-overwrite stock bitwise | Checkpoint A logits | Checkpoint B logits | Logits A/B bitwise |
| --- | --- | --- | --- | --- | --- | --- |
| control (stock bytes) | 0 / 1.0 | true | true | PASS | PASS | true / true |
| serial h=2 | 5.60445568e-08 / 1.0 | false | true | PASS | PASS | true / true |
| serial h=3 | 5.60445568e-08 / 1.0 | false | true | PASS | PASS | true / true |

Cada checkpoint comparou 201,088 logits F32 completos. Nos três braços, para A e B, o validador mediu max absolute error `0`, relative max `0`, cosine `1.0` e bitwise equality `true` contra stock. O máximo absoluto do vector de referência é `18.4183292388916` em A e `18.391559600830078` em B. O controlo confirmou que callback, overwrite dos próprios bytes stock e continuação são transparentes neste evento. h=2/h=3 injectaram outputs Tesy não bitwise iguais ao FFN stock, mas os logits observados ficaram bitwise iguais após os dois checkpoints; isto é uma observação, não um requisito de bitwise parity para Tesy.

As activations stock/handoff foram bitwise iguais nos braços Tesy. A paridade FFN, a paridade do output stock antes de overwrite, as checks de rota e weights, os dois rollbacks de capture, os decode return codes e a leitura bitwise do tensor injectado passaram. Não houve async, retry nem medição de tempo.

## Gates de validação e ambiente

Focused model-free: 11 testes de schema/validador, mutações e contrato callback/committed state passaram. Full model-free: Ruff, compileall, shell syntax, `git diff --check` e 294 testes passaram. Native build pinado passou. O build manifest validou HEAD Tesy, HEAD llama, hashes do source mixed/capture, CMakeLists, executáveis e paths; mixed executable SHA-256 `fab1444798524fd7adfb92b69f01f6a9524273d37ad13b5e2538b22129e0c61b`, capture SHA-256 `c262798adcfe5771a5aeb0375297ed278c64540a21556d0d262adc3eacc091ee`.

Runtime provenance `PASS`: executable e argv exactos, uma única `libggml-cuda.so` do build mapeada, SHA-256 `9534c103f6bf4c161d4fd14adc08e54d141ea57fc931e22ccba0ff0f1801d96c`, sem mismatches. Host identity `PASS` e virtualização `PHYSICAL`; pre-run sem processo GPU compute concorrente. Recursos `PASS`: 52 amostras, zero falhas GPU, zero swap de processo, mínimo 23,344,136,192 bytes de RAM disponível e 7,662,993,408 bytes de VRAM livre observada; máximo 51 °C e 31.18 W. Estes números são apenas health telemetry.

## Source feasibility A/B/C

Conforme `LIVE-MOE-REINJECTION-CONTINUATION-FEASIBILITY-20260924.md`:

- A, post-compute overwrite + continue: `SOURCE_FEASIBLE`, agora corroborado pela execução física neste evento.
- B, pre-compute skip mantendo downstream graph: `STATIC_NO_GO` na API pública `cb_eval`; `ask=true` escolhe pontos de observação, não salta o node.
- C, resume após `cb_eval=false`: `STATIC_NO_GO` na API pública; o scheduler quebra o loop sem cursor de resume.

## Limite de claim e stop

Este GO demonstra apenas que os outputs serial Tesy para a rota real da layer 0 podem ser escritos **depois de o MoE stock calcular** em `ffn_moe_out-0`, preservando numerical logits e greedy continuation pelo decode reinjetado e um token committed adicional neste prompt/modelo/pin. Não demonstra que stock MoE foi evitado, speedup, production non-regression, substituição end-to-end, rotas dinâmicas, várias layers, cache, misses, prefetch, tráfego físico ou novidade.

O STOP MILESTONE A foi atingido. A próxima decisão arquitectural pertence à auditoria externa; este PR não implementa graph skipping nem trabalho de performance.
