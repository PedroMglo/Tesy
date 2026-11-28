# Quanto custa verificar propostas na conversa de código?

**MEDIDO · NO_GO para o verificador de dois tokens com esta regra de proposta.** Em seis processos novos do GPT-OSS-120B original no portátil, o cliente recebeu as mesmas doze respostas válidas. No segundo turno, verificar as propostas atrasou o primeiro conteúdo final em **1,141–1,486 s** e a conclusão validada em **7,388–7,893 s** nos quatro contrastes. A fusão CPU e o pack de experts já estavam ativos nos três braços. O resultado fecha a adição deste componente para esta conversa. O ensaio numérico tinha admitido a medição depois de reproduzir logits completos, KV e continuação nos cortes reais de rejeição e aceitação integral. [Protocolo anterior à medição](protocol.md) · [Quatro referências numéricas](../block/README.md) · [Todos os dados compactos](result.json)

## O pedido, as referências e o que a pessoa esperou

W serve a combinação pack C291 e fusão CPU no executor de produção desta experiência. OFF usa a biblioteca reparada do candidato com propostas desligadas. ON ativa nessa biblioteca o verificador de três posições e a procura no histórico por bigrama com até dois IDs propostos. O 120B governa sempre as rotas e a confirmação. A família mede o preço marginal sobre a combinação. A comparação de W com o R0 operacional independente está na família anterior com a mesma tarefa. [Receitas e comparação R/P/W](../README.md)

Cada processo avaliou os 2 043 IDs de T1 e gerou 78, incluindo EOG. T2 usou a resposta real de T1, reutilizou 2 044 posições, avaliou 61 novas e gerou a mesma função de 256 IDs até EOG. O segundo pedido passou o validador isolado C131 nos seis processos. O primeiro final vai desde o POST à primeira peça de conteúdo final. A conclusão válida inclui transporte e validação. O decode e o prefill são do servidor. O cleanup final mede do último corte observado até à confirmação de que servidor, porta e scope fecharam.

| Processo | T1 válido, s | T2 prefill, s | Primeiro final, s | T2 válido, s | Decode, s | Decode, tok/s | Cleanup após último corte, s |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1W | 70,553 | 8,766 | 28,727 | 67,371 | 58,569 | 4,371 | 1,062 |
| 2OFF | 70,435 | 8,826 | 28,850 | 67,877 | 59,016 | 4,338 | 1,162 |
| 3ON | 71,472 | 9,285 | 30,213 | 75,264 | 65,945 | 3,882 | 1,295 |
| 4ON | 70,753 | 9,007 | 30,029 | 75,066 | 66,021 | 3,878 | 1,024 |
| 5OFF | 70,563 | 9,024 | 28,889 | 67,382 | 58,326 | 4,389 | 1,056 |
| 6W | 70,339 | 8,921 | 28,787 | 67,499 | 58,547 | 4,373 | 1,213 |

| Ordem | Controlo | Ganho de ON no primeiro final, s | Ganho até à validação, s | Ganho no decode, s | Proteção decode | Proteção T1 |
|---|---|---:|---:|---:|---|---|
| W/OFF/ON | W | -1,486 | -7,893 | -7,376 | FAIL | PASS |
| W/OFF/ON | OFF | -1,363 | -7,388 | -6,929 | FAIL | PASS |
| ON/OFF/W | W | -1,243 | -7,567 | -7,475 | FAIL | PASS |
| ON/OFF/W | OFF | -1,141 | -7,684 | -7,695 | FAIL | PASS |

## Trabalho efetivamente adiantado

O alvo aceitou 40 dos 92 IDs propostos em cada ON. Rejeitou a primeira proposta em 23 blocos, aceitou um ID em seis e os dois em 17. Houve 46 blocos e 169 avanços seriais em vez de 255 avanços seriais. O número de chamadas desceu. O tempo entre a primeira e a última amostra aumentou. A soma cobra cada intervalo entre amostras do mesmo relógio uma vez. Nos controlos, as colunas separam os intervalos nas mesmas posições em que ON faria uma proposta. O desvio assinado entre a soma nativa e o decode do servidor ficou entre −5 e +7 µs.

| Processo | 169 intervalos ordinários, s | 46 intervalos substituídos ou verificados, s | Média por bloco, ms | Decode menos a soma dos intervalos, µs |
|---|---:|---:|---:|---:|
| 1W | 38,938 | 19,630 | 426,745 | 7 |
| 2OFF | 39,134 | 19,882 | 432,208 | 0 |
| 3ON | 39,581 | 26,364 | 573,120 | -5 |
| 4ON | 39,575 | 26,446 | 574,915 | 5 |
| 5OFF | 38,772 | 19,554 | 425,086 | 3 |
| 6W | 38,894 | 19,653 | 427,240 | 6 |

Nos controlos W desta família, um bloco teria de custar em média até **426,745 / 427,240 ms** para empatar o decode mantendo o restante trabalho serial fixo. O verificador custou **573,120 / 574,915 ms**. Nessa hipótese favorável teria de poupar cerca de **26% do próprio custo por bloco**. Os intervalos ordinários também demoraram mais no candidato. Para 6 tok/s em código, o orçamento condicional de W nesta família foi 81,047 / 82,022 ms. Os 6 tok/s contratuais pertencem ao nominal de 153 tokens. A fonte anterior estimava 425,3 / 425,7 ms para empatar nos W anteriores. [Análise das propostas ao longo do turno](selection/README.md)

## Proveniência, custo e conservação

O protocolo foi congelado no commit `60ef215d`. A medição R02 usou `fa1314c85e28459ec925cea27fd47a93535899dc`, árvore `a03aaaeed18e2d9ed0e3fd0926ffc4a2592fcf60`. O recibo da família é `49aeda87c9b8845f86b4bed2b251149e93388c4804af5a1532504f8bc508449a`. Os servidores correram no Ryzen AI 9 HX 370 e na RTX 4060 Laptop de 8 188 MiB, driver 620.73.04, em AC e perfil performance. A janela C55 teve 62 amostras ao longo de 60,987 s, sem concorrente identificado. O GGUF original reside no NVMe interno Btrfs. Cada processo teve inventário C118 de pelo menos 60 s, cap de 20 GiB e contexto 8 192.

Duração da família 1443,955 s. Atingiu 15 778 029 568 B no cgroup, 6 854 MiB de VRAM e zero swap no cgroup. Máximos de 95,500 °C na CPU, 65,04 °C na GPU e 58,85 °C no NVMe. A potência amostrada da GPU dá 12643,3 J em 869,698 s de cobertura. O consumo total do portátil e os bytes físicos do NVMe por token ficaram desconhecidos.

A primeira família terminou antes do segundo servidor por cadência do inventário. Foi repetida do princípio, sem juntar o primeiro W aos pares seguintes. Na primeira auditoria, o sandbox exterior recusou o socket NETLINK_ROUTE necessário ao bwrap do validador C131. Nova revisão no portátil executou o validador isolado nas seis funções. A reabertura da cópia privada produziu a mesma auditoria, byte a byte. O novo arquivo contém 320 ficheiros, 16 734 103 B e 37 destinos de links registados, incluindo falhas. [Primeira tentativa física](retake.md) · [Comandos](commands.json) · [Manifesto](archive.json)

```sh
unit=research/ready-experts/cpu_wave/code_chat/price
python3 -IB "$unit/review.py" --check "$unit/result.json"
python3 -IB research/qualification-retake/private_archive/verify.py "$TESY_CODE_PRICE_ARCHIVE" "$unit/archive.json"
```

**Decisão de arquitetura.** Manter a combinação de pack e fusão disponível e R0 `slots40-persistent` como controlo operacional. Um proponente diferente pode alterar a distribuição de acertos. Um executor diferente teria de reduzir o custo do bloco e o trabalho que sobra nos passos seguintes. A promoção exige os relógios dos dois pedidos na configuração física e a proteção do outro caso. M3 PARTIAL e M4 NOT_MET.
