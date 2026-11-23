# C172–C175 — plano real e referência independente

Base: C171 `264c78d`, upstream `8019dc563b1ecbae6b161a70c3a1359f1b206c1e`, loader patch intacto na worktree `d12811df4e9f37cefd7ad4b5405b9e0825ea4fe5`. Bibliotecas preservadas de C166; nenhuma reconstrução ou alteração de kernels.

## SOURCE_AUDITED + metadata nativa, sem weights

`llama_model.no_alloc=true`, load_mode NONE: dummy buffers para weights/KV; retorno antes de load_all_data. O probe chama graph_reserve(split_only), nunca decode/compute. Graphs reais de 32/1 tokens,24 splits, todos36 layers. Método usa scheduler assignments, inputs/copied tensors e callback do optimizer CUDA real; não deduz execução pelo nome de buffer.

| Layers | Router | Experts MXFP4/gate/up/down+bias+SWIGLU | Ponderação/redução |
|---|---|---|---|
|0–23|CPU|CPU|CPU multiplicações e adds separados|
|24|CPU|CPU|CUDA0, fusão weighted reduction|
|25–35|CUDA0|CPU|CUDA0, fusão weighted reduction|

CUDA router F32: n=1 custom MMVF; n=32 dispatch MMF/cublas consoante regras do pin; callback raw logits/probs impede fusão matmul+bias neste schedule. Topk/weights seguem backend router. IDs/activations são copiados para CPU quando exigidos. Experts terminados e weights são copiados para CUDA no tail. O scheduler expande GPU para trás da layer25 até ao tail24, parando nos ops com weights CPU. A fusion matcher em ggml-cuda.cu:3032–3183 gera dependências no optimizer; range guard runtime protege inputs do output. `moe-weighted-reduction.cu` usa ordem experts0..3, F32 e `sum += expert * weight`, compilado com `-use_fast_math` (FMA permitido). Flags preservadas do build C148. CPU MXFP4 dot usa Q8_0 activations e vec_dot pinado; não é MMQ CUDA.

Storage dummy CUDA_Host difere do mmap CPU_Mapped real: ambos buffers host aceites por CPU; o plano e source de suportes, e não o label, fundamentam o mapa. Copied-tensor query pública retorna UNKNOWN; o nome gerado pelo scheduler e backend consumidor identificam o destino. UNKNOWN original preservado no raw. Nenhum byte metadata vira tráfego NVMe.

Detector: schema de campos exactos, shapes/dtypes/backends/schedule, comparação integral; quatro testes dirigidos cobrem nove mutações (backend, buffer, movimento, copy, fusion, kernel/op, dtype, operação ausente, CPU/GPU errada), além de extra field/schedule. Primeira validação rejeitou legitimamente copias ainda sem buffer; foi corrigida pelo contrato source do scheduler, sem nova leitura do modelo.

## REPRODUZIDO_MODEL_FREE

C173 preserva FAIL do controlo MXFP4 que esperava32 sem Q8_0 scale rounding. C174 derivou antes do teste o valor exacto `(32*127)*half(1/127)`, mas revelou uma assert do scheduler: backendCPU tem de ser último. C175 reparou apenas o fixture e passou: MXFP4/F16 dot conhecido, F32 weighted reduction CUDA bitwise contra std::fma independente, shapes1/32. CPU separado divergiu em384valores, controlo negativo que distingue aritmética. Nenhum GGUF payload nesses testes. Não são falhas do modelo.

Referência prospeciva: lê pesos/biases do GGUF canónico, recalcula routing e experts independentemente, segue map TSV gerado do plano nativo. Buffers são WEIGHTS como no loader nativo; CPU experts e router/tail são verificados no scheduler antes do compute. Checkpoints do observer e ggml_set_output preservam lifetime e impedem fusões de router incompatíveis. Views são expandidas antes dos adds como source nativo. Nenhum output nativo é devolvido como referência. Critério frozen: bitwise, sem epsilon novo. C169 não é reclassificado.

Estado: REFERENCE_PLAN_MATCHED_MODEL_FREE no scope do mapa e tail; causa do C169 continua hipótese até layer24 física. Próximo gate: layer24 com fivephases do capture C166 revalidado, monitoresFILE_PAGING e freshinventory. Se passar:25–35 e controleCPU0; não repetir0–23 por rotina.
