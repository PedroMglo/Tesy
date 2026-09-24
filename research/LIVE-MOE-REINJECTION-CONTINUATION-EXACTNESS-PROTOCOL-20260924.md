# Protocolo prospectivo: live MoE reinjection e committed continuation — 2026-09-24

## Objectivo e base

Base: branch `research/live-moe-handoff-timing-20260924`, commit `764cb09ade02d8b0a40deb7628baab613510ab09`, tree `f4407126d81c6382d4af751208bda371b9832794`. Pergunta: pode o output serial Tesy do evento real da layer 0 ser escrito pós-compute em `ffn_moe_out-0` e preservar logits/greedy sampling pelo decode reinjetado e por mais um decode committed normal?

Classificação antes da campanha: `SOURCE_FEASIBLE / IMPLEMENTED_NOT_RUN`. A auditoria do pin está em `LIVE-MOE-REINJECTION-CONTINUATION-FEASIBILITY-20260924.md`. Este gate não mede performance e deixa o stock MoE calcular.

## Pins e autoridade

llama.cpp `4e416ee7308dd6b581796f1a6241276cd5982691`. Modelo `gpt-oss-20b-mxfp4.gguf`, 12,109,564,352 bytes, SHA-256 `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`. Prompt `benchmarks/prompts/b0-b1-diagnostic.txt`, SHA-256 `431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6`. Contexto stock CPU `n_gpu_layers=0`, `n_ctx=4096`, 12 threads, greedy. Primeiro token `2167`; depois de decodificar `2167`, segundo token `1309`. O terceiro token é definido pelo stock uninterrupted da própria campanha.

## Braços e sequência

Quatro contextos frescos no mesmo processo físico, na ordem stock, control, h2, h3. Um único modelo pinado é partilhado, mas o contexto/KV de cada braço é criado de novo. Stock não instala `cb_eval`; faz prefill, sample 2167, decode normal de 2167, copia logits A, sample 1309, decode normal de 1309, copia logits B e sample do terceiro token. Não há rollback.

Control faz prefill e stock-reference capture da activation, top-k, weights e `ffn_moe_out-0`; exige early-stop return 0 e rollback explícito da repeated position. No decode committed repetido, verifica activation, IDs, weights bitwise e pre-overwrite stock output, escreve os próprios bytes stock em `ffn_moe_out-0`, verifica leitura bitwise do tensor escrito, devolve `true` e termina o graph. Exige exactamente uma injection, retorno 0, logits A, 1309. Desliga a reinjection, decodifica normalmente 1309 sem rollback, copia logits B e exige o terceiro token stock.

h2/h3 acrescentam handoff capture e rollback antes do decode committed, com paridade activation e rota/weights exactos. O executor serial Tesy usa GPU slots 0..1 / CPU slots 2..3 para h2, GPU slots 0..2 / CPU slot 3 para h3. Executa fora de qualquer timing, lê output e exige FFN parity contra stock. O committed decode deixa o stock MoE calcular, valida a rota e o pre-overwrite output, substitui por Tesy output, devolve `true` e completa o graph. O decode reinjetado não é revertido; 1309 é decodificado normalmente sobre esse estado e os logits B/terceiro token são comparados.

O callback exige exact name `ffn_moe_out-0`, F32 contiguous e 2880 elementos. Cada vector injectado e de logits tem de ser finito. Duplicate injection, route drift, decode não-zero, rollback falhado, output ausente ou bytes escritos divergentes terminam a campanha.

## Métricas de correctness e decisão

Para FFN, pre-overwrite e full logits A/B: relative max `<= 0.005`, cosine `>= 0.9999`, todos finitos. Greedy tokens são exactos. O controlo regista bitwise equality de FFN/logits; Tesy regista bitwise equality mas esta não é gating. Full logits F32 são persistidos por braço/checkpoint; Python reabre os ficheiros, verifica contagem e finite, e recomputa independentemente max absolute error, max absolute reference, relative max, cosine e bitwise equality. C++ não declara GO.

`LIVE_MOE_REINJECTION_CONTINUATION_EXACTNESS_GO` só se stock, control, h2 e h3 passarem todas as condições. Qualquer falha invalida a campanha; não existe performance NO_GO neste protocolo. Raw schema `tesy.live_moe_reinjection_continuation_exactness_raw.v1`; summary schema `tesy.live_moe_reinjection_continuation_exactness_summary.v1`. Campos de performance são rejeitados pelo validador.

## Proveniência, recursos e falha

Runner exige Tesy/llama worktrees clean, HEAD/tree exactos no root, pin llama, SHA/tamanho do modelo, SHA prompt, host físico, GPU sem concorrência, build hashes de source/CMake/binários, argv/executable exactos e única CUDA library mapeada do build. Monitoriza telemetria GPU completa, zero swap de processo, pelo menos 2 GiB RAM disponível e 1 GiB VRAM livre. Não deriva tráfego físico.

Cada tentativa usa root novo. Um root falhado fica preservado com `failure.json`, stderr e quaisquer artefactos já escritos. Defeitos técnicos corrigidos exigem novo commit, regressão e novo root. Falha genuína do control, h2/h3, rota, logits, greedy ou estado committed termina o trabalho para auditoria.

## Limite de claim e stop

Mesmo se GO, isto demonstra apenas post-compute tensor overwrite e numerical/greedy continuation para uma rota real na layer 0 e um token subsequente. Não demonstra skip do MoE stock, speedup, production non-regression, substituição end-to-end, rotas dinâmicas, várias layers, cache, misses, prefetch, tráfego físico ou novidade. O primeiro GO válido, blocker arquitectural ou falha genuína de correctness/recurso é o STOP MILESTONE.
