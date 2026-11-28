# Quanto da residência CPU se resolve escolhendo a camada?

**NO_GO para as quotas aprendidas em T1 e para substituir o backend com base em quotas fixas de LRU.** Na conversa nominal, escolher as melhores quotas com conhecimento de todo o segundo turno ainda exige 1 268 leituras CPU. O banco de 252 frames acoplado ao primário atual serve a mesma procura com 1 110. A diferença de 158 existe antes de cobrar qualquer reposição. As quotas aprendidas pouparam 35 leituras antes do primeiro conteúdo contra a divisão igual. A entrega das identidades em falta para continuar do estado de referência anulou essa poupança e custou mais 49 leituras no total. Estes resultados são TRACE_DERIVED. Conservam-se M3 PARTIAL e M4 NOT_MET. [Protocolo congelado](protocol.md) · [Resultado por fase e por braço](evidence-20261128-r01/decision.json)

| CPU do segundo turno | Igual | Quotas de T1 | LRU global | Melhores quotas futuras | Melhor residência global futura |
|---|---:|---:|---:|---:|---:|
| Natural nominal, leituras | 1 373 | 1 341 | 1 415 | 1 268 | 657 |
| Natural nominal, incluindo reposição mínima | 1 373 | 1 422 | 1 500 | 1 320 | 676 |
| Nominal153 fornecido, leituras | 1 144 | 1 162 | 1 295 | 1 047 | 824 |
| Nominal153 fornecido, incluindo reposição mínima | 1 144 | 1 267 | 1 388 | 1 095 | 824 |
| Code153 fornecido, leituras | 2 263 | 2 267 | 2 139 | 2 096 | 1 246 |
| Code153 fornecido, incluindo reposição mínima | 2 263 | 2 372 | 2 202 | 2 212 | 1 248 |

As duas linhas de cada par têm objetivos distintos. Em cada coluna com futuro, reotimizámos separadamente as leituras da janela e as leituras mais a reposição no fim. O oráculo global conhece a utilização exata seguinte de cada peso e pode servir uma falta nos frames de trabalho sem a conservar. A troca que retém o peso com uso mais próximo nunca aumenta as faltas, porque até à primeira reutilização desse peso o outro tem uso mais tardio ou nenhum. Uma wave pede um conjunto simultâneo e todos os seus membros cabem na área de trabalho. Depois da wave, todos os candidatos a retenção estão disponíveis. Uma procura virtual final pelos membros da referência cobra cada identidade em falta uma vez. O teste compara esta conta com enumeração exaustiva em sequências pequenas. Há 644 leituras de diferença entre os dois ótimos com reposição no natural. A conta admite transferências de propriedade e movimentos físicos gratuitos e mede exclusivamente a oportunidade de escolher **que expert** conservar. [Algoritmos e teste](policy.py) · [Curvas por camada](evidence-20261128-r01/curves.json.gz)

| Fase CPU | Igual | Aprendida | Primário atual e banco contínuo |
|---|---:|---:|---:|
| Natural, prefill 5 | 31 | 37 | 26 |
| Natural, prefill 148 | 612 | 625 | 532 |
| Natural, decode até ao primeiro final | 722 | 668 | 540 |
| Natural, cauda | 8 | 11 | 12 |
| Nominal153 fornecido, prefill / decode | 572 / 572 | 620 / 542 | — |
| Code153 fornecido, prefill / decode | 1 467 / 796 | 1 491 / 776 | — |

**O custo de formar e continuar o estado.** No primeiro turno observado, a divisão igual e a candidata pediram 2 178 leituras CPU no prefill e 1 296 no decode. O banco de referência pediu 2 140 e 1 177. A candidata expulsa 81 membros ao alterar as quotas na entrada de T2 e precisa de 81 membros para repor a referência no fim. São custos diferentes. Em T2 os 760 registos CUDA do controlo natural ficam fora desta intervenção. As reposições indicam payload ausente. Posições físicas, idades, gerações, cópias, preparação, cronologia das publicações e tempo do cliente requerem uma comparação própria. A área útil continua limitada a 1 212 frames mais 40 transitórios, num total de 1 252. A avaliação reconstituiu as 2 987 waves naturais nos dois journals, incluindo as vazias, e verificou as respetivas procuras. Os dois casos fornecidos verificam as testemunhas OFF/ON, 153 posições e 32 passos. O turno natural de código de 61 posições continua a precisar de um journal próprio para esta comparação.

O primeiro processo selou os três planos, capacidades e ordem dos residentes antes do incremento. Outro processo abriu os incrementos, validou a ordem de ranks e procuras, reconstruiu o selo e comparou a execução com as curvas de stack. O SHA-256 do plano é `a2eef3f0ec35083a7037c8bb3f00371a22472c902ba29eee72df77f88e2d21f2`. O código correu em `054a672ce2e915b5396d8aa713c8f18e163e013b`, árvore `3fe69f6fc224c4e3b42905ad84bb0366646c4d6b`. A preparação demorou 4,02 s e atingiu 157 776 KiB de RSS. A avaliação demorou 6,49 s e atingiu 184 404 KiB. Zero leituras de pesos e zero forwards. P97 e P106 observam o mesmo trabalho em dois processos. Os tempos medidos do cliente permanecem os do ensaio integrado. [Selo dos três prefixos](plan-20261128-r01/plan.json) · [Controlos físicos integrados](../../cpu_wave/README.md)

```sh
p=research/ready-experts/request_path/partition
python3 -IB "$p/test_partition.py" -q
python3 -IB "$p/screen.py" --check "$p/evidence-20261128-r01"
# Reprodução integral com o arquivo privado, em dois destinos novos
python3 -IB "$p/screen.py" --archive "$TESY_ARCHIVE" --seal "$WORK/plan"
python3 -IB "$p/screen.py" --archive "$TESY_ARCHIVE" --new "$WORK/replay" \
  --plan "$WORK/plan/plan.json" --plan-sha256 a2eef3f0ec35083a7037c8bb3f00371a22472c902ba29eee72df77f88e2d21f2
```
