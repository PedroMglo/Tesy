# Resultado: CPU split graph com stock MoE realmente omitido — 2026-09-24

## Decisão e âmbito

**MEDIDO:** `LIVE_MOE_SPLIT_GRAPH_SKIP_EXACTNESS_GO` no host físico de referência, campanha `results/live-moe-split-graph-skip-exactness-20260924T205335Z/`. Branch `research/live-moe-split-graph-skip-exactness-20260924`, PR #32 draft na Stack #22, base PR #31. Measurement commit `2654a547e5c4c16ccc71436bf4e870f76e5ee608`, tree `ca837a60fb778d10abc68c2129b31efacbbf0d7f`, worktree Tesy limpo durante a execução. Não houve failed campaign root nesta fase.

O validador Python `src/tesy/live_moe_split_graph_skip_exactness.py` recomputou paridade FFN e de todos os 201,088 logits F32 por checkpoint a partir de vectores persistidos. O C++ não publicou a decisão. Os seis braços usaram processos/contextos frescos e reproduziram `2167 → 1309 → 316`. O decode split de `2167` ficou committed; o decode normal posterior de `1309` usou esse estado e produziu `316`.

## Pins, builds e source feasibility

Modelo `gpt-oss-20b-mxfp4.gguf`, 12,109,564,352 bytes, SHA-256 `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`; prompt `benchmarks/prompts/b0-b1-diagnostic.txt`, SHA-256 `431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6`. Stock llama.cpp HEAD `4e416ee7308dd6b581796f1a6241276cd5982691`, tree `1b99d359957a92710b1e6551089819ec98fa1c78`, checkout limpo. `n_gpu_layers=0`, 12 threads, contexto 4096, greedy, layer 0. O build stock não contém `llama_tesy_set_graph_compute_hook`; o build Tesy-patched exporta-o, e o hook nulo manteve a chamada stock do scheduler.

Patch interno `patches/llama-cpp-4e416ee73-tesy-split-graph-hook.patch`, SHA-256 `2de013af9a434b3d3fa757d83c873b561e777031f8199e90b106b1754efc60d2`. O diff observado do worktree patched é byte-for-byte igual ao patch, sobre o mesmo HEAD/tree upstream; hashes dos ficheiros patched `src/llama-context.cpp` `39d91709100d93567c2a200770c1d8db69aa229b9939e5c58539f853a863de94` e `src/llama-context.h` `40a1e9d0486fdce779e18d1e367038b8e07646ec6970b6a3659ac3d9b12c44ab`. Não se alterou o único checkout stock.

GCC/G++ 15.3.1, CUDA 13.3.73, arch 89. Executável stock SHA-256 `5071096f520605f0f1dbb2612f21efabae25a3a062939935484d735e9c61bc73`; patched `5aab9ce8ecff971579500fcd7aa0d8d191d7865c90e5da2912bf92aeee6349c7`. `libllama.so` stock `498f9f505ba4e331a4881c9242616773b3333adcf3a5da46991f2f8e42a479c6`; patched `2a1b26817cfc27578fad71b3af3ce6a0ea3b180d001966c432814d2227a3fbab`. Os hashes de CMake, source nativo, `libggml-cpu.so` e `libggml-cuda.so`, bem como paths, estão em `build-provenance.json`.

S1–S7 estão auditados no documento `LIVE-MOE-SPLIT-GRAPH-SKIP-FEASIBILITY-20260924.md`: full allocation antecede `set_inputs` e compute; `ggml_graph_view` é uma vista contígua sem alocação; backend CPU directo aceita as views; não houve `sched_reset` no split; memory/KV, logits e output bookkeeping ficaram no `llama_decode`; a construção gpt-oss expande weights, experts e aggregation antes do residual; S7 foi corroborado por inventário/dependências no graph real, não por índices mágicos. O scheduler de graph completo não foi usado para executar as views.

## Killer test e graph real

**REPRODUZIDO model-free:** MF0 full scheduler, MF1 prefix/middle/suffix CPU directo e MF2 prefix + output middle injectado + suffix deram output bitwise igual. Em MF2, a função custom do middle teve 0 chamadas; no MF1 teve 1. Buffers mantiveram os endereços e a alocação do scheduler permaneceu válida. O teste está ligado ao native CI, sem disparar manualmente esse CI.

**MEDIDO no graph gpt-oss:** 1,349 nodes; `attn_post_norm-0` índice 30, `ffn_moe_topk-0` 35, `ffn_moe_weights_softmax-0` 39, `ffn_moe_out-0` 55. Prefix `[0,40)`, middle `[40,56)`, suffix `[56,1349)`. Todos os 1,349 nodes foram atribuídos a `CPU` no scheduler e estavam alocados. O middle tem 16 nodes, incluindo 3 `MUL_MAT_ID`, `ADD_ID`, `GLU`, weighted MUL, views e agregação final; o primeiro node é um `RESHAPE` de `attn_post_norm-0`, o último é `ffn_moe_out-0` (`ADD`). Cada node middle é ancestral de `ffn_moe_out-0`, nenhum node suffix tem dependência directa de outro middle node, e um downstream node consome `ffn_moe_out-0`. O inventário integral, com nomes, ops e backend de cada node, está em `inventory.json` de cada braço split.

| Braço | Prefix / middle / suffix | Escrita externa | FFN relative max / cosine / bitwise | Logits A / B vs stock | Tokens |
| --- | --- | --- | --- | --- | --- |
| stock unmodified | scheduler full | 0 | não aplicável | autoridade | 2167/1309/316 |
| patched null-hook | scheduler full | 0 | não aplicável | bitwise / bitwise | 2167/1309/316 |
| segmented same-work | 1 / 1 / 1 | 0 | 0 / 1.0 / true | bitwise / bitwise | 2167/1309/316 |
| skip-stock | 1 / **0** / 1 | 1, stock bytes | 0 / 1.0 / true | bitwise / bitwise | 2167/1309/316 |
| serial Tesy h=2 | 1 / **0** / 1 | 1, Tesy bytes | `5.604455676769968e-08` / `0.9999999999999988` / false | bitwise / bitwise | 2167/1309/316 |
| serial Tesy h=3 | 1 / **0** / 1 | 1, Tesy bytes | `5.604455676769968e-08` / `0.9999999999999988` / false | bitwise / bitwise | 2167/1309/316 |

FFN h=2/h=3 max absolute error `1.9073486328125e-06`, reference max absolute `34.032718658447266`. Para todos os braços, os checkpoints A e B tiveram logits relative max `0`, cosine `1.0`, bitwise equality `true`; max absoluto de referência `18.4183292388916` em A e `18.391559600830078` em B. Bitwise logits é observação deste evento, não threshold requerido para Tesy. Nos braços split, rota `[1,13,17,21]`, weights `[0.347873956,0.320948303,0.174925864,0.156251907]`, activation/weights congelados bitwise, captures com rollback PASS e reinjection escrita/verificada uma vez nos skip arms. O segmento stock com 3 `MUL_MAT_ID` não foi invocado nos skip arms; a prova persistida são ranges, inventário e contadores, não wall-clock.

## Proveniência, recursos e validação

`doctor.json`: referência PASS, virtualização `PHYSICAL`, CPU/GPU alvo, NVMe, sem processo GPU compute concorrente. Todos os seis `runtime-provenance.json`: `PASS`, executable e argv exactos, único `libggml-cuda.so` do build correcto mapeado, sem mismatch. Stock CUDA SHA-256 `9534c103f6bf4c161d4fd14adc08e54d141ea57fc931e22ccba0ff0f1801d96c`; patched `84f6e30603ac9ffc98bad42d3983fe0c2e6da8a602269e0aec79833f6e26f38a`. Recursos PASS em 143 amostras, zero GPU telemetry failures, zero swap de processo; mínimo RAM disponível `23,907,528,704` bytes, mínimo VRAM observada livre `7,662,993,408` bytes, máximo 53 °C e 28.3 W. São apenas health telemetry, não tráfego físico nem performance.

Focused model-free: 8 testes PASS; full: Ruff, compileall, shell syntax, `git diff --check`, 302 testes PASS. Build nativo stock e Tesy-patched PASS. O CI GitHub não foi disparado manualmente; PR permanece draft. Não existem failed campaign roots. Reparações técnicas pré-campanha: include interno `ggml-impl.h` marcado SYSTEM para conservar `-Werror` Tesy, callback custom model-free robusto a `nth` do backend, e toolchain GCC 15 em vez do GCC 16 não suportado por `nvcc` 13.3. As duas tentativas de configuração/compilação falhadas eram builds locais, não campanhas; a única campanha física criou root novo e passou. Não houve alteração de thresholds, workload, rota, modelo ou pin depois de observar outputs.

## Claim boundary e stop

Este GO demonstra apenas que **um decode gpt-oss real da layer 0, em stock CPU graph**, pode executar prefix/suffix views sobre full allocation, omitir o range stock que produz `ffn_moe_out-0`, receber um output serial Tesy h=2/h=3 e preservar numerical logits, greedy tokens e uma continuação committed adicional no evento congelado. Não demonstra speedup, production non-regression, stock graph GPU-offloaded, outras rotas/layers, cache, misses, prefetch, tráfego físico, inferência end-to-end optimizada ou novidade. **STOP MILESTONE A atingido**; timing e generalização exigem decisão externa e não foram iniciados.
