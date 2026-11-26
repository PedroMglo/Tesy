# As recargas entre tiles antecipam as primeiras faltas do decode C304?

**NO_GO para esta seleção causal nos dois casos C304.** Mesmo concedendo a preparação gratuita de todos os experts que a regra identifica, retenção ilimitada depois da entrada no decode e READ a 80% da duração observada, o controlo greedy precisa de pelo menos **6,934 s em intervals** e **7,697 s em inventory**. A janela de 32 passos a 6 tok/s permite 5,333 s. Os dois processos com o estimador reproduzem a decisão. O fecho aplica-se também a qualquer subconjunto dessas escolhas, sob as mesmas hipóteses. A conversa nominal M4 tem outro workload.

A regra ampla seleciona a chave camada/expert se o serviço R0 publicou os seus pesos em pelo menos duas tiles distintas da chamada incremental e se a chave estiver fora do primário na entrada do decode, I. A regra restrita exige também publicação na última tile. O seletor registou as publicações por rota e geração antes de abrir o sufixo. A camada 35 só participa na última linha. A contagem de escolhas coincide nos dois processos de cada caso. [Protocolo das recargas](reload-protocol.md) · [Recibo de seleção](evidence/select.json)

| Caso | Regra | Escolhas CPU / CUDA | Primeiras faltas cobertas CPU / CUDA | Payload para materializar CPU / CUDA (B) |
|---|---|---:|---:|---:|
| intervals | Ampla | 290 / 30 | 145 / 17 | 3 833 568 000 / 396 576 000 |
| intervals | Última tile | 41 / 0 | 23 / 0 | 541 987 200 / 0 |
| inventory | Ampla | 68 / 12 | 21 / 1 | 898 905 600 / 158 630 400 |
| inventory | Última tile | 10 / 2 | 4 / 1 | 132 192 000 / 26 438 400 |

## Janela de 32 passos

Valores em segundos. O R0 observado usa o relógio do journal entre o início do primeiro decode e o fim do 32.º. As colunas emparelhadas apresentam o piso de duração com o READ a 100% / 80%. O controlo sem seleção recebe a mesma retenção ilimitada. O oráculo amplo pode escolher as primeiras faltas que mais adiantam a barreira, até ao número de entradas concedido em **cada camada** à regra ampla. O recibo inclui o oráculo análogo para a última tile e as folgas com precisão integral. [Avaliação por braço](evidence/evaluate.json)

| Braço | R0 observado | Controlo sem seleção | Regra ampla | Regra última tile | Oráculo amplo |
|---|---:|---:|---:|---:|---:|
| intervals greedy | 11,217813 | 9,0772 / 7,6296 | 8,2081 / 6,9344 | 8,9639 / 7,5391 | 6,1667 / 5,3012 |
| intervals estimador | 11,174977 | 9,0987 / 7,6519 | 8,2564 / 6,9781 | 8,9820 / 7,5585 | 6,1970 / 5,3305 |
| inventory greedy | 10,976578 | 9,2738 / 7,7846 | 9,1639 / 7,6967 | 9,2530 / 7,7680 | 8,4377 / 7,1157 |
| inventory estimador | 11,553964 | 9,7602 / 8,1813 | 9,6352 / 8,0814 | 9,7335 / 8,1600 | 8,8448 / 7,4490 |

Em intervals, o oráculo com acesso às identidades futuras só cabe à escala 0,8, com 32,109 ms de folga no greedy e 2,803 ms no estimador. Em inventory, mesmo o oráculo a 0,8 fica 1,782 s acima da janela no greedy e 2,116 s no estimador. A regra ampla do inventory cobre uma primeira falta CUDA, mas a sua eliminação dá **zero** ganho no máximo da barreira em ambos os processos.

**REPRODUZIDO.** Cada braço tem 1 152 grupos e 4 608 seleções ordenadas do target. Em intervals o R0 faz 1 338 cargas, das quais só 989 são primeiras faltas depois de I sob retenção ilimitada. Em inventory são 1 320 e 1 055. Em cada par coincidem os digests de P, I, F, dos ranks e da sequência greedy. A avaliação reproduziu, nos dois controlos greedy, o objeto completo de baseline de serviço fixo do cenário C304 nas escalas 0,8, 1 e 1,2. Os estimadores são medições dos mesmos dois casos com relógios próprios. O recibo preserva também a duração observada por `decode_window_s`, cujo âmbito externo difere ligeiramente do journal. [Cenário C304](../../../results/c304-prefix-cost-observer-repair-20261007/heldout-scenario.json)

**TRACE_DERIVED, condicional.** Para cada primeira falta obrigatória, somam-se as três componentes READ em série com desconto de até 1 µs por componente. Por grupo cobra-se o maior serviço sobrevivente, incluindo as mudanças do último expert. O resto do caminho usa a partição C295 fora de P11–P12, com a cauda. A união de READ obrigatório fora da espera é zero nos quatro braços. Os tempos fixos são 1,840 / 1,865 s em intervals e 1,828 / 1,866 s em inventory (greedy / estimador). Uma implementação teria de pagar materialização, retenção e cópias, escolher vítimas e contabilizar faltas induzidas e reconstituição de F. O teto dispensou esses custos. Não se atribuiu tempo a qualquer falta induzida nem se mediram bytes físicos de NVMe. [Verificador](evaluate.py)

## Observação que falta

A hipótese distinta de reaparição de um expert roteado após uma **ausência** entre tiles fica **INCONCLUSIVE / NOT_RUN_MISSING_TILE_MEMBERSHIP**. Nas camadas 0–34 o C304 preserva 175 marcadores P2 e zero observações P3 durante as cinco tiles de 32+32+32+32+25. Um hit residente pode ficar silencioso. Há quatro P3 na camada 35 para a linha final. Logo, a publicação positiva P10 está identificada, mas a ausência de P10 não identifica ausência de routing. Os scores C304 dos dois casos cobrem o decode nas CPU 2–24. Os witnesses WRT40 de desenvolvimento pertencem a outras sequências de entrada. A nota de cobertura discrimina esses artefactos. [Auditoria de cobertura](coverage.md) · [Protocolo de identificação](protocol.md)

Para reabrir a hipótese de reaparição nas mesmas conversas, a observação mínima de pertença é um bitmap de 128 experts oficiais por camada e tile, antes do parking, 2 800 B/caso nas 35 camadas, com call, geometria, poda final e vinculação ao estado I e aos logits do incremento. Uma política que selecione identidades fora do universo das recargas, ou uma intervenção que altere o custo de serviço, tem uma premissa própria.

## Reprodução e orçamento

Checkout de medição `939f5afbd4b56c051df0d2eaa5e132550734d2d6`, árvore `822387d9eee96d205afa3c96fecbfd5bf2ffbc34`. O primeiro processo autentica os 12 ficheiros contra o manifesto e só interpreta os eventos até ao P16 da chamada 0. Após selar os quatro braços, o segundo autentica novamente os três ficheiros de cada braço e verifica o percurso até F. As execuções R01 e R02 produziram os mesmos bytes nos dois recibos e no selo privado de 225 395 B. Os compactos publicados contêm apenas digests e contagens das trajetórias, sem vetores de tokens, prompts ou saídas do modelo. [Identidades, tamanhos e custos](evidence/reproductions.json)

Os quatro braços da curva de desenvolvimento com routing completo também falham o teste mais favorável da última tile. A decisão de investimento é dispensar a captura adicional para esta hipótese. [Teste de desenvolvimento](../entry_tile_membership/README.md)

Na checkout limpa, usar a raiz privada `TESY_C304_RAW` e dois destinos novos por reprodução.

```sh
export LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
script=research/qualification-retake/c304_causal_entry/screen.py
python3 -B "$script" --phase select --raw-dir "$TESY_C304_RAW" --new-output-dir "$NEW_SELECT"
python3 -B "$script" --phase evaluate --raw-dir "$TESY_C304_RAW" --new-output-dir "$NEW_EVAL" \
    --sealed-selection "$NEW_SELECT/selection.json" \
    --selection-sha256 da07eb19a21b6aadb678e509bd0c102f97e7dde31f856d6979131f1ea42a315c
```

Seleção R01/R02 em 0,23 / 0,23 s com máximo RSS de 22 204 / 21 728 KiB. Avaliação em 1,41 / 1,41 s com 113 676 / 113 572 KiB. Os limites por processo foram 120 s CPU, 512 MiB AS e 8 MiB de saída por ficheiro. As reproduções eram processos separados e correram em paralelo entre si na mesma estação. Zero GPU, pesos ou forwards nesta unidade. M3 PARTIAL e M4 NOT_MET.
