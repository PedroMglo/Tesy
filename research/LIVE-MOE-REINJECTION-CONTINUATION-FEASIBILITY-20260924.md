# Feasibility de reinjection e continuation — 2026-09-24

## Objectivo e base

Pergunta: no llama.cpp pinado, pode o callback público sobrescrever os bytes de `ffn_moe_out-0` depois do compute stock, antes dos consumidores posteriores, e continuar o mesmo decode? Base Tesy: `764cb09ade02d8b0a40deb7628baab613510ab09`; llama.cpp: `4e416ee7308dd6b581796f1a6241276cd5982691`. Evidência: `SOURCE_AUDITED`, ainda não validação física de reinjection.

## A — post-compute overwrite + continue: SOURCE_FEASIBLE

Em `ggml/src/ggml-backend.cpp`, `ggml_backend_sched_compute_splits` pergunta `callback_eval(t, true, ...)` para encontrar um node pedido (linhas 1809–1816), calcula o graph view até esse node (1820–1824), sincroniza o backend (1827) e chama `callback_eval(t, false, ...)` (1829). Só interrompe o loop se o callback devolver `false`; se devolver `true`, avança para os nodes seguintes. `ggml_backend_sched_graph_compute_async` devolve o resultado desse loop. `src/llama-context.cpp` instala o callback no scheduler (1421) e usa o resultado do graph para extrair logits (1454–1462, 1545–1555).

Em `ggml/include/ggml-backend.h` a API pública expõe `ggml_backend_tensor_set`; em `ggml/src/ggml-backend.cpp` (335–347) escreve os bytes no buffer alocado, incluindo views, com verificação de limites. O graph gpt-oss nomeia o output agregado `ffn_moe_out` em `src/llama-graph.cpp` (2339–2358). Assim, em contexto stock CPU (`n_gpu_layers=0`), o callback pós-compute pode validar F32/contiguidade/2880 elementos, ler o stock output, escrever um vector F32 e devolver `true` antes do range seguinte. A viabilidade source é estreita; o controlo físico com o próprio stock output ainda tem de confirmar transparência e continuation.

## B — pre-compute skip de um node mantendo downstream graph: STATIC_NO_GO na API pública

O retorno do callback `ask=true` apenas escolhe se o node divide o range para observação. O scheduler continua a computar o graph view que inclui esse node. Não existe retorno público `skip-and-continue` nessa API. Este gate não altera o scheduler nem tenta saltar o compute MoE stock.

## C — resume depois de `cb_eval=false`: STATIC_NO_GO na API pública

O callback `false` quebra o loop em `ggml_backend_sched_compute_splits` (1829–1830); a função devolve `GGML_STATUS_SUCCESS` sem cursor/resume handle. O próximo `llama_decode` é outra chamada, não uma continuação do graph interrompido. Este comportamento foi também reproduzido no gate anterior; não se implementa resume.

## Decisão e próximo teste discriminante

Implementar apenas o gate de correctness de post-compute overwrite. Primeiro testar o controlo que reinjecta os próprios bytes stock, depois h=2/h=3 serial Tesy. O gate não mede tempo nem demonstra que evita compute stock. Qualquer divergência do controlo após reparação de defeitos técnicos é falha de correctness e termina a campanha.
