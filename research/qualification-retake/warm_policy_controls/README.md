# Controlos de vítimas na entrada do decode C294

**NO_GO para os dois controlos ao limiar congelado.** Em 32 passos fornecidos, expulsar por ID aumentou as cargas nas quatro observações. A LRU com idades iniciais empatadas reduziu as cargas no código em 1,91% e aumentou-as no nominal em 2,59%. O critério exigia pelo menos 10% em cada caso. A ordem ou as idades dos residentes anteriores a I não foram usadas para a LRU. [Pré-registo](protocol.md) · [Resultados dos quatro braços](evidence-r3/receipt.json)

| Braço C294 ON | Publicações reais R0 | Ótimo com a entrada I | ID fixo, faltas (CUDA) | LRU de decode, faltas (CUDA) | Máximo para o gate |
|---|---:|---:|---:|---:|---:|
| nominal153-2 | 1081 | 787 | 1404 (449) | 1109 (333) | 972 |
| nominal153-3 | 1081 | 787 | 1404 (449) | 1109 (333) | 972 |
| code153-2 | 1308 | 928 | 1555 (473) | 1283 (372) | 1177 |
| code153-3 | 1308 | 928 | 1555 (473) | 1283 (372) | 1177 |

Cada braço começa com os seus 1411 residentes e 29 vagas comprovados em 1440 slots. Os 4608 acessos pertencem a 32 passos, 36 camadas e quatro ranks por camada. Ambos os controlos preenchem as 29 vagas. Nos braços nominais, a política de ID tem 3204 hits e 1375 expulsões. A LRU tem 3499 hits e 1080 expulsões. Nos braços de código são 3053/1526 e 3325/1254, respetivamente. Cada admissão custa 13 219 200 B de payload lógico. O recibo indica os totais por destino e o hash dos residentes finais. [Reconstrução das gerações e publicações](../cache_boundary.md) · [Âncoras de ranks](../warm_route_reference/protocol.md)

A LRU termina sem 92 identidades da cache final real no nominal e sem 100 em código. Para o ID fixo faltam 456 e 512. O custo mínimo para reconstituir apenas o conjunto é uma carga por identidade em falta na ausência de outra cópia utilizável. O replay não pagou essa continuação. As contagens não fornecem tempo crítico, bytes físicos de NVMe ou alinhamento de gerações e slots. O mínimo offline deixa uma oportunidade de 294 e 380 cargas face ao R0, mas exige informação futura. Distinguir uma política causal que a aproveite continua a exigir a comparação no mesmo estado real. [Limite de cache](../cache.md)

C163 usou pureLRU44 na seleção de desenvolvimento, com novos serviços de misses desconhecidos. Os holdouts C164 testaram apenas CPU52/GPU44 sobre o estado de 44 slots. O controlo atual iguala a capacidade e as identidades entre braços e dá uma resposta para outros pedidos com um critério de cargas. A política do prefixo e do incremento pode reutilizar exatamente as mesmas regras de pin de toda a rota, desempate e custo através da função pública `replay(residents, groups, *, scores=None, decode_lru=False, capacity=40)`. [C163](../../C163-OVERHEAD-RESULT-C164-HOLDOUT-FREEZE-20260930.md) · [C164](../../C164-REPLAY-AND-POLICY-DECISION-20260930.md) · [Condição da política P+I](../warm_routes40/protocol.md)

R1 recusou o primeiro recibo dos ranks por ter excedido o seu orçamento. A execução parou antes do primeiro braço. R2 ligou à reprodução R4 que passou e encontrou MemoryError antes do primeiro braço devido ao espaço de endereçamento das threads da biblioteca numérica importada. R3 manteve o mesmo limite de 256 MiB, escolheu uma única thread para a dependência e terminou em 0,475 s com pico de 61 436 KiB. As quatro observações produziram os resultados acima. Zero forwards, GPU e leituras de pesos. [FAIL de origem](evidence-r1/receipt.json) · [Correção do vínculo](anchor-r2.md) · [R2](evidence-r2/diagnostic.json) · [Ambiente R3](environment-r3.md)

```sh
LC_ALL=C OPENBLAS_NUM_THREADS=1 python3 -c 'import subprocess,sys; sys.exit(subprocess.call(sys.argv[1:]))' \
  python3 -B replay.py --raw-dir "$C294_RAW" --new-output-dir "$NEW_RESULT"
```
