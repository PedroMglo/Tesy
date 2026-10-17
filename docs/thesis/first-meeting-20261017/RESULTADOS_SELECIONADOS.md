# Resultados selecionados para a primeira reunião

Este ficheiro contém apenas resultados adequados para uma apresentação inicial. Não substitui os relatórios científicos internos.

## Residência de experts: 32 → 40 slots

Fonte: `research/C129-SLOTS40-CONFIRM-RESULT-20260929.md`.

Workload: dois turnos, prefix reuse 2044 IDs + 153 novos IDs, 47 output tokens.

| Métrica | Ganho mediano emparelhado |
|---|---:|
| Warm decode | **23,173%** |
| Warm first-final | **18,009%** |
| Warm prefill | **13,331%** |
| Cold decode | **23,900%** |
| Cold first-final ~2K | **11,074%** |
| Cold prefill ~2K | **9,251%** |

Limite: mudar slots altera simultaneamente a capacidade do pool e a geometria das waves; não atribuir todo o ganho exclusivamente a cache hits.

## Residência de experts: 40 → 44 slots

Fonte: `research/C142-UNIFORM44-CONFIRM-RESULT-20260930.md`.

| Métrica | Ganho mediano emparelhado |
|---|---:|
| Warm decode | **11,745%** |
| Warm first-final | **8,575%** |
| Warm prefill | **5,676%** |
| Cold decode | **8,125%** |

Medianas absolutas do candidato: **5,236 tok/s** de decode, **19,312 s** first-final, **10,335 s** prefill.

Limite: slots44 é experimental; não recebeu a cobertura geral do perfil slots40 e não atingiu M4.

## Reutilização de experts entre tiles

Fonte: `research/C274-BLOCKS-EXPERT-REUSE-CLOSURE-20261004.md`.

C271, trabalho fornecido: melhoria mediana de **18,190%** no prefill153; decode mediano **−0,542%**, dentro da proteção daquele teste. C273, utilidade livre de código: first-final **+8,915%** e tempo até resultado validado **+5,245%**. Em planeamento, candidato 2/2 correto enquanto controlo atingiu o cap 2/2, sem rácio de latência válido.

Limite importante: a qualificação causal posterior C282 mostrou que o perfil R2 não generalizou de forma admissível — no caso nominal o decode regrediu ~10,7%. Não apresentar o protótipo como perfil promovido.

## Hipóteses rejeitadas que vale a pena mencionar

Fonte principal: `research/C320-EXACT-EXPERT-SERVICE-ARCHITECTURAL-CLOSURE-20261007.md`.

- política lógica de residency/hotness: sem ganho global suficiente;
- serviço contíguo de experts: ganho integrado de ~6–7%, abaixo do gate;
- prefetch/gate aproximado: regressão no caminho real;
- predictor affine aprendido: melhor previsão, mas execução real mais lenta;
- Zstd lossless: ~4,3–4,5% de poupança nos pesos alinhados da amostra; envelope condicionado insuficiente para justificar integração.

## Estado que deve ser dito sem rodeios

- caminho operacional: `slots40-persistent`, opt-in;
- M3: parcial;
- M4: **NOT_MET**;
- slots44: experimental;
- EAGLE3 testado: `NO_GO` no desenho/âmbito medido;
- novidade ampla: **não reclamada**.

## Números que não devem ser mostrados sem contexto

- somas de bytes lógicos como se fossem tráfego físico NVMe;
- microbenchmarks isolados como previsão do Transformer completo;
- resultados de um único workload como ganho geral;
- estimativas de prefetch como se fossem speedups medidos;
- qualquer comparação externa não congelada como baseline científico.