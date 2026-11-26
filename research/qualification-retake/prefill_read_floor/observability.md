# O que o servidor C281 observa no prefill

**REPRODUZIDO por inspeção, sem abrir o modelo.** O servidor C281 no pin C269 `d0ebfbcc6c8f456bc1083027c1b08075a32824d8` não contém o emissor do journal C135. Na receita C281 o único opt-in Tesy é `TESY_CPU_WAVE_SKIP_PARKED=1`. Os builds C135/C136 usavam o outro pin `ba058e62c33f6e1c6d8581c4685d9abb64542027`, compilado com `TESY_C84_EXPERT_TRACE`. Nesse build o journal é ativado por `TESY_C84_EXPERT_TRACE_FILE` e o ficheiro indicado por `TESY_C122_TRACE_TRIGGER_FILE` abre a janela no início da chamada seguinte. O cliente C135 criava o trigger antes do segundo pedido. Estes dois nomes não existem nos ELFs C269 revistos. [Receita C281](../../../results/c281-persistent-r0-runtime-20261005/c281-r0-persistent-config.json) · [Ativação C135](../../../tools/c135_slots40_trace.py) · [Emissor C122](../../../patches/C122-warm153-decode-trace.patch)

| Objeto verificado | SHA-256 |
|---|---|
| servidor | `054e983528d35731e2dc6222f1418f2f08120ef83e0c5f2a8db11805dd38effa` |
| libllama-server-impl | `6e4786b127d8a0f2addd657b9842dade1c3f2b9262d088b84fb526ca04ed9206` |
| libllama C269 | `347267b2e9cbf920dbf912d6aaf1884e5eff4cccc41c349e93c42bd6403a658f` |
| libggml-cpu C269 | `9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313` |

No source C269, `src/llama-moe-stream.cpp:538,707` soma a diferença entre duas leituras de `ggml_time_us()` à volta de cada espera condicional. `print_stats:419` formata totais de hit/miss, stall normal e por wave. Só `common_perf_print` chama a API correspondente, e o servidor persistente não a invoca. `LLAMA_MOE_STREAM_DEBUG` regista expulsões. Os flags `--perf` e `--log-timestamps` controlam as estatísticas/etiquetas existentes. No stderr de 4 107 B do C281 contemporâneo encontrámos 11 330,69 ms de prompt para 153 IDs e 10 390,74 ms de decode para 47 tokens no T2. Não existem aí spans por call, componente ou operador, nem as duas somas de stall. O cliente SSE mediu 21,443 s até ao primeiro final, no relógio de transporte. As 5+148 chamadas foram observadas no C135; o total 153 no log C281 não demonstra essa repartição neste braço. [Digests e relógios C281](../nvme_conversation/evidence-20261124-r1/evidence.json)

Reprodução de leitura com a checkout C269, a pasta bin do servidor C276 usada no C281 e o stderr privado cujo SHA começa por `c5dd8a669055`:

```sh
git -C "$C269" rev-parse HEAD
cpu="$C269/build-c269-cuda/bin/libggml-cpu.so.0.15.3"
llama="$C269/build-c269-cuda/bin/libllama.so.0.0.9884"
sha256sum "$SERVER_BIN/llama-server" "$SERVER_BIN/libllama-server-impl.so" "$llama" "$cpu" "$C281_STDERR"
strings -a "$SERVER_BIN/llama-server" "$SERVER_BIN/libllama-server-impl.so" "$llama" "$cpu" |
  rg 'TESY_C84_|TESY_C122_|TESY_CPU_WAVE_SKIP_PARKED'
nm -C "$cpu" | rg 'ggml_graph_compute_thread|ggml_compute_forward_mul_mat_id'
rg -n 'moe stream: (waves|load stall|remap calls)|prompt eval time|eval time =' "$C281_STDERR"
```

**Primeiro discriminante para MMID · HIPÓTESE.** No CPU -O3 o símbolo local `ggml_graph_compute_thread.isra.0` sobrevive e o kernel MMID está inlined. O source `ggml/src/ggml-cpu/ggml-cpu.c:3030–3096` contém o despacho do nó e a barreira existente. Um pequeno overlay isolado pode datar entrada/saída de cada thread de compute em `GGML_OP_MUL_MAT_ID` num vetor de tamanho fixo por thread, usando o CLOCK_MONOTONIC de `ggml_time_us()`. Guardar identidade de execução/grafo/nó, projeção e número de linhas, reconstruir as uniões de parede e distinguir a última conclusão da saída da barreira. Usar um identificador explícito para associar layer/wave/call na futura integração. Ensaiar primeiro a fixture CPU C57B com gate/up/down, broadcast, pares estacionados e zeros, igualdade bitwise OFF/ON, cobertura dos threads e rejeição de overflow ou ausência de término. O custo é duas leituras de relógio por thread/nó observado e registos em RAM, a medir. Pedir uma entrega cb_eval por nó subdivide o grafo e chama `ggml_backend_synchronize` em `ggml/src/ggml-backend.cpp:1682–1712`. [Fixture C57B](../../C57B-SYNTHETIC-FFN-DISCRIMINANT-20260928.md) · [Âmbito distinto do C46 frio](../../C46-WAVE-PHASE-RESULT-20260928.md)

**Só para atribuir a um pedido.** Portar e qualificar separadamente, no mesmo pin, os pares READ/SET das três componentes, reserva/publicação sob mutex, consumo e WAIT com identidade de geração, quatro workers de I/O, call/tile/camada/wave. Medir interseção com MMID no mesmo domínio monotónico, conservar duração dos restantes nós e não somar worker-tempo. A ausência de overlap com os READ não prova que todo esse MMID é removível. Qualificar OFF/ON do mesmo novo binário contra o R0 original, incluindo IDs, logits finitos e fases; manter as fases do cliente separadas. No custo de uma intervenção usar AB/BA contemporâneo trace-OFF por caso, todos os sinais individuais e a proteção do outro caso. A fixture de custo código é C273 1952+153 e 32 passos fornecidos, tal como a nominal C271 tem 2044+153; o cliente nativo de custo usa uma chamada incremental de 153. Nenhuma substitui as fronteiras do servidor natural. No par histórico C135/C136 o decode ON foi 0,967 s mais lento; o custo deste novo observador permanece por medir. A prova aplica-se a esta pergunta MMID e deixa independentes as hipóteses de serviço dos pesos. [Contratos de fase](../../C282-R2-CAUSAL-QUALIFICATION-CLOSURE-20261005.md) · [Controlo C135/C136](../../C135-C136-SLOTS40-RESIDUAL-DECODE-20260929.md)
