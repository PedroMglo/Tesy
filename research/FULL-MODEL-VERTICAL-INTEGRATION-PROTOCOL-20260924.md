# Integração vertical: protocolo de engenharia

Base: PR #32, commit `4e6501fc3afaab22bf152fc8e5a9ebb1cd336222`, tree `5084b5ef8e6587895b9390fa79adbad6ab0cf307`. Branch de trabalho `engineering/full-model-vertical-integration-20260924`. Classificação: engenharia prospectiva; a comparação end-to-end final continua `NOT_RUN`.

## C1 — executor e baseline

Corrigir o graph de agregação para receber dois parciais F32 independentes. Teste nativo model-free: graph da soma com um único node ADD, leaves `GGML_OP_NONE`, FFN contado uma única vez após compute separado, cópia explícita e soma. O caminho completo serial/async inclui a cópia do parcial GPU; nenhuma latência histórica descreve esta implementação corrigida.

Baseline stock: llama.cpp `4e416ee7308dd6b581796f1a6241276cd5982691`, sem patch, modelo GGUF SHA-256 `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4` e 12 109 564 352 bytes. `scripts/run_full_model_stock.sh` usa o tokenizer e geração do backend com template Jinja incorporado `gpt-oss`, `--reasoning off`, contexto 4096, 12 threads, greedy (`temperature=0`, `top-k=1`), seed 42, `--fit off` e colocação explícita. Este é um smoke funcional, não a calibração nem a avaliação final. O prompt histórico cru mantém-se como regressão separada; o smoke usa `benchmarks/prompts/vertical-short-summary.txt`.

Antes de cada modelo: worktree clean, pin stock clean, modelo SHA/tamanho, host de referência físico, ausência de outro processo compute GPU, root novo, telemetria. Uma falha preserva a root e requer identidade nova. Amostras terminais sem `/proc/PID/status` não contam para ausência de swap. Não chamar cold load ao processo se page cache não foi controlada.

## C2 — candidato (por executar)

O candidato normal deverá consumir activation, IDs e routing weights do próprio prefixo stock no decode em curso; omitir o middle MoE stock, executar Tesy serial com residência GPU estática por identidade e CPU para os restantes, injectar o FFN e continuar o suffix committed. Não pode pré-calcular FFN do mesmo token, nem usar capture/rollback/replay no caminho normal. Correctness instrumentada separada do timed path; relative max ≤ 0,005, cosine ≥ 0,9999, greedy sequence exacta e route authority stock. O controlo negativo deverá demonstrar que o suffix consome o tensor injectado. Se a seam CPU-only impedir a substituição correcta de todos os eventos admitidos, parar apenas o candidato e completar o baseline.

## C3 — avaliação (ainda não congelada)

Antes de executar, publicar um manifesto único de workloads públicos versionados, configuração B_causal/B_competitive/Tesy, calibração separada, até quatro casos, até seis colocações testadas, ordem equilibrada, 128 tokens máximos e cinco repetições independentes por condição final. EOS preservado; load separado da inferência. Sem full-logit dumps, FFN sombra ou callbacks diagnósticos escondidos no timed path. A avaliação não será iniciada sem correctness e proveniência completa. `pending_external_audit` mantém-se verdadeiro mesmo após PASS local.
