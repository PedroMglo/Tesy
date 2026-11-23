# Feasibility: split graph stock CPU para skip de MoE — 2026-09-24

## Pergunta e base

**HIPÓTESE**, ainda não medida: no decode de `2167` do `gpt-oss-20b-mxfp4.gguf`, o graph stock completamente alocado pode ser executado em três views contíguas no backend CPU, ou em prefix/suffix com `ffn_moe_out-0` preenchido externamente, sem executar o middle MoE stock. Isto é um gate de correctness; não mede performance.

Base Tesy `5fdd11016954348405edc9d4ea9fced6dc28c63d`, tree `bbe309161cdca2d50099dca80a0676b7b064596e`; llama.cpp pinado `4e416ee7308dd6b581796f1a6241276cd5982691`, worktrees limpas na rediscovery. Branch de trabalho `research/live-moe-split-graph-skip-exactness-20260924`. A alternativa de `cb_eval` público foi excluída pelo gate anterior: permite post-compute overwrite, não pre-compute skip+continue nem resume depois de `false`.

## Auditoria S1–S7 no source pinado

| Item | Evidência source-level e conclusão |
| --- | --- |
| S1, vida da alocação | `src/llama-context.cpp::process_ubatch()` aplica o memory context, constrói/reutiliza o graph, chama `ggml_backend_sched_alloc_graph(sched, gf)` antes de `res->set_inputs()`, e só depois `graph_compute()`. O graph e os buffers permanecem vivos nesse intervalo. **SOURCE_FEASIBLE**, sem `sched_reset`/realloc durante o hook. |
| S2, view | `ggml/src/ggml.c::ggml_graph_view()` devolve uma estrutura com `nodes = cgraph0->nodes + i0` e `n_nodes = i1 - i0`; não cria nem realoca tensors. **SOURCE_FEASIBLE** para índices verificados. |
| S3, CPU directo | `ggml/src/ggml-backend.cpp::ggml_backend_graph_compute()` chama o compute do backend e sincroniza. Isto pode executar uma `ggml_graph_view` sobre buffers já alocados. **CONDICIONAL**: todos os nodes relevantes e as suas storage/dependencies têm de ser efectivamente CPU no runtime, não apenas `n_gpu_layers=0`. A atribuição é consultável com `ggml_backend_sched_get_tensor_backend()`. |
| S4, reset | `ggml_backend_sched_reset()` põe `is_alloc=false` e limpa bookkeeping de backend quando necessário. Não é uma operação segura entre prefix e suffix; a próxima alocação pode reatribuir buffers. **PROIBIDO** durante o split. |
| S5, commit | `process_ubatch()` substitui apenas compute e devolve `res` após sucesso; `llama_context::decode()` prossegue com cópia de logits, output bookkeeping e estado memory/KV. `mctx->apply()` ocorre antes do graph, e falhas seguem o ramo de rollback. Um hook mínimo que devolva `GGML_STATUS_SUCCESS` mantém este caminho, sem reimplementar `decode()`. **SOURCE_FEASIBLE**, sujeito ao controlo físico de committed continuation. |
| S6, topologia | `src/models/openai-moe.cpp` coloca `attn_post_norm` antes de `build_moe_ffn`, e usa `ffn_moe_out` no `ggml_add` residual subsequente. `src/llama-graph.cpp::build_moe_ffn()` nomeia top-k e weights softmax, expande o graph em `weights`, depois em `experts`/views/adições até `ffn_moe_out`. **SOURCE_FEASIBLE**, mas índices, unicidade, ops e backend exigem inventário do graph real. O segundo `cb(cur, "ffn_moe_out", il)` em `openai-moe.cpp` renomeia o mesmo tensor, não cria outro node. |
| S7, middle contíguo | `ggml_build_forward_expand(gf, weights)` materializa o prefix até os pesos; a função MoE expande depois `experts`, respectivas views e agregação até `moe_out`, antes de devolver ao caller; só então o caller constrói o residual/suffix. `ggml_visit_parents_graph()` insere nodes em ordem topológica por DFS, sem mover os já inseridos. Assim o candidato a middle é `[weights_idx+1, moe_out_idx+1)`. **SOURCE_FEASIBLE CONDICIONAL**: no graph real deve ser provado que cada node desse intervalo é ancestral de `ffn_moe_out-0`, que nenhum node do suffix depende directamente de outro node middle, que os quatro anchors são únicos e ordenados, que há `MUL_MAT_ID`, e que o downstream consome `ffn_moe_out-0`. Se alguma condição falhar, `STATIC_NO_GO` para esta seam; não ajustar os limites por números mágicos. |

## Risco adicional: scheduler não é executor de views após alocação

`ggml_backend_sched_graph_compute_async()` usa `sched->is_alloc` para decidir se aloca e, quando já alocado, chama `ggml_backend_sched_compute_splits(sched)` sobre splits previamente preparados. Passar-lhe uma view nova não lhe altera os splits. A hipótese experimentada será, portanto, `ggml_backend_graph_compute(backend_cpu, &view)` após alocação completa. O hook nulo mantém a chamada stock a `ggml_backend_sched_graph_compute_async()` sem alteração semântica.

## Próximos gates e limites

Antes do modelo: MF0 full scheduler, MF1 prefix/middle/suffix CPU directo same-work, MF2 middle não executado e output exacto escrito no tensor; comparação bitwise, buffers válidos e contador de middle zero. Só depois: testes de schema/fault, build stock e patched separados, controlo físico null-hook, same-work, stock-output skip e serial h=2/h=3. **NOT_RUN** à data deste documento. Não se infere skip físico do source; a prova será o inventário e os contadores de views do runtime.

Mesmo um GO futuro significaria apenas correctness no evento congelado da layer 0 e committed continuation; não speedup, baseline production, outras rotas/layers, cache ou prefetch.
