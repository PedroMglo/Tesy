## Pergunta

Pode o decode real da layer 0 executar `stock prefix -> authoritative router -> Tesy serial FFN -> stock suffix`, omitindo o middle stock que produz `ffn_moe_out-0`, sem alterar logits/tokens nem a continuação committed? Gate apenas de correctness/arquitectura; sem performance.

## Implementação

- Source audit S1–S7 e killer test CPU model-free MF0/MF1/MF2.
- Patch interno mínimo sobre llama.cpp `4e416ee7308dd6b581796f1a6241276cd5982691`, guardado em `patches/`, aplicado num worktree/build separado. Hook nulo mantém o scheduler stock; `llama.h` público não mudou.
- Seis processos/contextos frescos, sequenciais: stock unmodified, patched null-hook, segmented same-work, skip-stock, serial Tesy h=2 e h=3. Full-graph allocation antecede views directas do backend CPU; route/weights vêm do graph stock. Sem async, cache, prefetch ou timing.
- Validador Python independente sobre raw, inventário, vectores FFN/logits completos, proveniência e recursos.

## Validação e resultado

**MEDIDO:** `LIVE_MOE_SPLIT_GRAPH_SKIP_EXACTNESS_GO` em `results/live-moe-split-graph-skip-exactness-20260924T205335Z/`, measurement commit `2654a547e5c4c16ccc71436bf4e870f76e5ee608`. 1,349 nodes stock, todos CPU; prefix `[0,40)`, middle `[40,56)` com 3 `MUL_MAT_ID`, suffix `[56,1349)`. Nos três skip arms, prefix/middle/suffix `1/0/1`, escrita externa 1. Os seis braços reproduziram `2167 -> 1309 -> 316`; full logits A/B de 201,088 F32 ficaram bitwise iguais ao stock. FFN serial h2/h3 relative max `5.604455676769968e-08`, cosine `~1`, bitwise false. Captures, rota, weights, runtime provenance, recursos e zero swap PASS. Nenhum failed campaign root.

Focused 8 testes PASS; full Ruff/compileall/shell syntax/`git diff --check`/302 pytest PASS; builds stock e patched PASS. CI GitHub não foi disparado manualmente. PR draft, sem merge.

## Limite da claim

Prova apenas correctness de split/skip no evento gpt-oss congelado da layer 0, em stock CPU graph, com Tesy serial h2/h3 e mais um token committed. Não prova speedup, non-regression de produção, outras layers/routes, GPU-offloaded stock graph, cache, misses, prefetch, tráfego físico, end-to-end optimizado ou novidade. STOP MILESTONE A; nenhuma etapa posterior implementada.

Auditoria completa: `research/LIVE-MOE-SPLIT-GRAPH-SKIP-FEASIBILITY-20260924.md`, `research/LIVE-MOE-SPLIT-GRAPH-SKIP-EXACTNESS-PROTOCOL-20260924.md`, `research/LIVE-MOE-SPLIT-GRAPH-SKIP-EXACTNESS-RESULT-20260924.md`.
