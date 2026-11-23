# C3 — baseline do modelo inteiro entregue; Tesy bloqueado por correctness

Estado: **MEDIDO** para o stock full-model; **NOT_RUN** para comparação end-to-end Tesy. Branch `engineering/full-model-vertical-integration-20260924`, base PR #32 `4e6501fc3afaab22bf152fc8e5a9ebb1cd336222`, PR draft #33. Measurement commit `95a2a4a7118690f256ef2f08d73c14e7664ea099`, tree `3330a72243bd8ffdf7012918c60bd06d57b54826`. Auditor independente implementado em `7227cd785549b0481ff031ea501beaf614b72d48`. Grupo admitido `results/full-stock-chat-eval-valid-20260924T222803Z/`. `pending_external_audit=true`.

## Resultado da unidade de engenharia

O graph de agregação Tesy foi corrigido para usar leaves independentes e cópia explícita do parcial GPU. O teste nativo model-free verificou topology/execução e uma única execução do FFN GPU. Timings antigos não descrevem este executor corrigido. Foi implementado um protótipo live serial de prefixo stock → router stock → Tesy FFN → suffix stock, com residência estática por identidade `{0,1,2,3}` por layer e partição h=0…4 testada sem modelo. Não se pré-calcula output FFN no caminho candidato.

O candidato **não passou a correctness multi-layer**. Na root preservada `results/vertical-live-diagnostic-20260924T215315Z/`, layers 0/1 h=0 tiveram FFN bitwise stock; na layer 2 a rota `[4,0,31,17]` teve h=1 e FFN Tesy relative max `4,12584316e-05`, cosine `0,999999995483`, mas os logits completos falharam o limite congelado: relative max `0,00855978666` > `0,005`, cosine `0,999976613624`. Pesos GPU residentes coincidiram em bytes com o GGUF; um FFN sombra all-CPU coincidiu bitwise com stock e não foi injectado. A primeira divergência foi no primeiro decode com três layers substituídas. Não se alteraram residência, thresholds nem workload para procurar PASS. O controlo negativo, 24 layers, candidate timed path e comparação B_causal/Tesy ficaram **NOT_RUN**. A única root de uma layer e dois tokens que passou é diagnóstico interno, não qualifica integração vertical.

## Baseline stock utilizável

Modelo instalado exacto: `gpt-oss-20b-mxfp4.gguf`, 12 109 564 352 bytes, SHA-256 `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`. Backend stock sem patch `llama.cpp` `4e416ee7308dd6b581796f1a6241276cd5982691`; executável `llama-server` SHA-256 `facdeefaff9d54818f7786f8812125231f28281ae496b62946fbb7e7127fe456`, CUDA mapeada SHA-256 `7bfb9b2970e65b2e0db7835eba76a09be6a1c410c8ac846b10c78e76459296a0`. Host físico de referência admitido em cada run: Ryzen AI 9 HX 370, RTX 4060 Laptop, 32 GiB RAM, NVMe; sem processo compute GPU concorrente no início. O runner `scripts/run_full_model_stock_server.sh` fornece geração chat normal com template **incorporado no GGUF**, Jinja, `--reasoning off --reasoning-budget 0`, 12 threads, contexto 4096, greedy, seed 42, `--fit off`, colocação explícita e sem prompt cache. O prompt histórico cru continua regressão separada.

O primeiro override genérico `--chat-template gpt-oss` contou apenas quatro tokens de input para um prompt de 221 tokens de texto e foi excluído. Com template incorporado, mas sem budget de reasoning, 128 tokens foram todos `reasoning_content`, sem resposta visível; essas roots também foram excluídas. Os reparos e identidades novas estão no protocolo. Os prompts finais têm 302 tokens templated (extracção longa; 221 no texto cru) e 132 (código curto; 51 no texto cru). A calibração sucessora, separada da avaliação, testou só `n_gpu_layers` 0/8/12: backend generation 17,029 / 24,515 / 29,460 tokens/s num prompt público de resumo com 57 tokens/EOS. Assim `n_gpu_layers=12` foi congelado como **B_competitive entre três colocações efectivamente testadas**, não como óptimo global; `n_gpu_layers=0` é B_causal da seam CPU-only.

## Avaliação stock-only prospectiva

Manifesto congelado: `research/coordination/FULL-STOCK-CHAT-EVAL-MANIFEST-20260924.json`. Dois prompts públicos diferentes da calibração; cinco processos frescos por condição; ordem de workloads/comparadores alternada; máximo 128 tokens, EOS preservado, page cache não controlada. Todos os 20 runs passaram model/host/capacity/runtime/resource gates e zero swap. A razão de paragem foi estável: extracção `69/stop`; código `128/length`. Para cada workload, o texto gerado foi idêntico em todos os runs e nas duas colocações stock, mas isto não é uma avaliação formal de qualidade.

| Workload | Baseline | Load→health med/p95 s | TTFT med/p95 s | Request generation med/p95 s | Backend per-token med/p95 ms | Tokens / stop |
|---|---:|---:|---:|---:|---:|---|
| Extracção longa | B_causal ngl0 | 1,397 / 1,526 | 2,514 / 2,559 | 6,212 / 6,284 | 62,555 / 63,570 | 69 / EOS |
| Extracção longa | B_competitive ngl12 | 1,894 / 2,023 | 1,615 / 1,644 | 3,738 / 3,754 | 36,189 / 36,278 | 69 / EOS |
| Código curto | B_causal ngl0 | 1,394 / 1,500 | 2,361 / 2,418 | 9,402 / 9,695 | 59,722 / 61,828 | 128 / limite |
| Código curto | B_competitive ngl12 | 1,891 / 2,008 | 1,474 / 1,480 | 5,444 / 5,627 | 33,667 / 35,214 | 128 / limite |

`TTFT` é tempo desde pedido HTTP até ao primeiro **conteúdo visível** SSE; `Request generation` vai do pedido até ao fim do stream, incluindo prefill, decode e transporte local. `Load→health` vai do lançamento do processo até ao servidor pronto e fica **fora** do tempo do pedido; não é cold load controlado. `Backend per-token` é o valor do backend `predicted_per_token_ms`, não a distribuição de latências token a token. A mediana é a terceira de cinco observações independentes; p95 nearest-rank com n=5 é o máximo. Com cinco processos no mesmo portátil e page cache não controlada, não há intervalo de confiança robusto nem generalização térmica. Não tratar tokens correlacionados como 128 réplicas.

| Rep | Tarefa | ngl | Load→health s | TTFT s | Request s | Backend ms/token | Tokens/stop |
|---:|---|---:|---:|---:|---:|---|
| 1 | extracção | 0 | 1,371 | 2,514 | 6,265 | 63,16 | 69/EOS |
| 1 | extracção | 12 | 2,023 | 1,610 | 3,655 | 34,96 | 69/EOS |
| 1 | código | 0 | 1,468 | 2,394 | 9,437 | 59,75 | 128/limite |
| 1 | código | 12 | 1,906 | 1,468 | 5,444 | 33,67 | 128/limite |
| 2 | código | 12 | 1,890 | 1,480 | 5,412 | 33,42 | 128/limite |
| 2 | código | 0 | 1,500 | 2,337 | 9,402 | 59,72 | 128/limite |
| 2 | extracção | 12 | 1,914 | 1,625 | 3,754 | 36,28 | 69/EOS |
| 2 | extracção | 0 | 1,437 | 2,508 | 6,212 | 62,56 | 69/EOS |
| 3 | extracção | 0 | 1,397 | 2,559 | 6,212 | 62,31 | 69/EOS |
| 3 | extracção | 12 | 1,894 | 1,598 | 3,738 | 36,26 | 69/EOS |
| 3 | código | 0 | 1,394 | 2,361 | 9,259 | 58,54 | 128/limite |
| 3 | código | 12 | 1,867 | 1,476 | 5,482 | 33,99 | 128/limite |
| 4 | código | 12 | 1,891 | 1,454 | 5,419 | 33,66 | 128/limite |
| 4 | código | 0 | 1,377 | 2,342 | 9,288 | 58,72 | 128/limite |
| 4 | extracção | 12 | 1,894 | 1,615 | 3,749 | 36,19 | 69/EOS |
| 4 | extracção | 0 | 1,526 | 2,478 | 6,117 | 61,40 | 69/EOS |
| 5 | extracção | 0 | 1,372 | 2,530 | 6,284 | 63,57 | 69/EOS |
| 5 | extracção | 12 | 1,887 | 1,644 | 3,698 | 35,15 | 69/EOS |
| 5 | código | 0 | 1,363 | 2,418 | 9,695 | 61,83 | 128/limite |
| 5 | código | 12 | 2,008 | 1,474 | 5,627 | 35,21 | 128/limite |

O máximo observado no grupo foi RSS de processo 12 925 100 032 bytes, GPU usada 6 020 923 392 bytes e 57 °C; mínimo 45 amostras válidas de processo por run. Amostras terminais sem `/proc/PID/status` foram excluídas da alegação de swap; todas as amostras GPU requeridas tiveram estado OK. Isto é saúde de recurso, não tráfego físico nem estimativa de RAM total residente por mmap. O output de extracção é um JSON relevante mas omite alguns materiais pedidos; o output de código termina antes dos dois exemplos. Portanto **não** declarar qualidade útil completa apenas por haver geração.

## Capacidade e loader

Relatório reproduzível em `src/tesy/vertical_capacity.py` e `research/FULL-MODEL-VERTICAL-CAPACITY-20260924.md`. Para o instalado: encoded artifact 12 109 564 352 bytes; peak stock C1 RSS 12 764 119 040 bytes; quatro residentes GPU de **uma layer** consumiram buffer nativo observado de 53 015 424 bytes. Não derivar repacking isolado de RSS menos artifact nem DRAM residente de mmap. O loader actual exige namespace completo de tensors antes de decode; materialização física total fica **DESCONHECIDO**. Candidatos maiores não foram descarregados/executados. Limites NVMe são cenários parametrizados, não tok/s.

## Evidência e limitações

O resumo compacto por run e agregados está no Git em `research/coordination/C3-STOCK-EVIDENCE.json`; os dois textos públicos completos gerados, com hashes e EOS/limite, estão em `research/coordination/C3-STOCK-OUTPUTS.json`. O auditor `src/tesy/full_stock_eval_audit.py` recalcula o resumo dos raw. O bundle completo da evidência decisiva está disponível no [prerelease de evidência](https://github.com/PedroMglo/Tesy/releases/tag/evidence/full-model-vertical-20260924-v1), com [asset descarregável](https://github.com/PedroMglo/Tesy/releases/download/evidence/full-model-vertical-20260924-v1/tesy-vertical-raw-evidence-20260924.tar.gz) de 1 646 346 bytes e SHA-256 `83b88fe09da4b1e038aec810537c7a30d702a7811dc78d4ebc29189f184a7bf6`, verificado após download. Inclui 20 runs com raw SSE/arrivals/telemetria/proveniência, ambos os vectores completos F32 de logits da falha e o relatório de capacidade; `bundle-manifest.json` enumera SHA/size de cada entrada. O `summary-final.json` incluído tem SHA-256 `47d63e066c45bd52f03302b9e19fce1f14de5b2e39847bfc66a8555c3830fbff`.

Os 21 `doctor-public.json` no bundle **omitem explicitamente** a enumeração de mountpoints não relacionados; os `doctor.json` originais continuam locais e byte-idênticos. Não foram publicados pesos, binários, builds ou caches. O endpoint SSE não capturou vector completo de token IDs; texto/contagens não permitem reconstruí-lo com autoridade. Roots falhadas anteriores não decisivas continuam apenas locais. Assim, a evidência decisiva de logits/stock pode ser recalculada remotamente, mas estes limites de provenance e token IDs permanecem abertos. Ver `research/coordination/C3-RAW-EVIDENCE-RELEASE.json`; `pending_external_audit=true`.

Roots técnicas preservadas: `results/full-model-stock-smoke-20260924T231500Z/` (sandbox sem host físico), `results/full-stock-chat-calibration-ngl0-20260924T221417Z/` e `...-diagnostic-20260924T221550Z/` (reasoning-only), `results/full-stock-chat-eval-20260924T222128Z/` (cinco runs interrompidos por provenance de biblioteca mapeada ausente), além das oito roots de falha Tesy listadas em C2. Runs antigos com template genérico e uma calibração válida apenas para esse template foram preservados, mas **excluídos** da seleção final. Reparos: leaves independentes da agregação; template incorporado; budget de reasoning explícito; persistência SSE na falha; verificação de executable/argv/CUDA mapeada; auditor de estatística/recursos. Validação final local: Ruff PASS, compileall PASS, shell syntax PASS, pytest **314 passed**, teste nativo model-free PASS anteriormente; Git diff check PASS. CI não foi disparada manualmente.

**Claim máximo:** existe geração stock reproduzível do modelo inteiro sob duas colocações admitidas e há um blocker numérico concreto para o candidato Tesy multi-layer congelado. Não há comparação end-to-end Tesy válida, speedup Tesy, cache/prefetch, tráfego físico, execução >RAM ou novelty claim. A decisão arquitectural seguinte pertence à auditoria externa.
