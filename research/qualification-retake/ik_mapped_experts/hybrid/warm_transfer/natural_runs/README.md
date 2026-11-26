# Tamanho e cadência de SET no T2 nominal com ClassLRU

**TRACE_DERIVED.** Com 288 slots e as rotas observadas no Tesy, todos os
11 961 SET de pesos no decode de T2 têm exatamente 4 406 400 B, distribuídos
por 3 987 reposições. A 161 slots há uma única dupla de experts contíguos
nos dois lados da transferência. A dimensão unitária da fixture de páginas
quentes cobre assim a maioria do payload em T2. A cadência difere. Os
1 656 sítios de decode sincronizam a leitura dos IDs antes do plano, e o
hook submete os SET de todos os pesos e o mapa antes de devolver controlo
ao scheduler. Uma latência que inclui um drain isolado por reposição fica
condicionada a essa cadência artificial. [Fixture de transferência](../protocol.md)

| Recorte da conversa | Fills 161 / 288 | SET de pesos 161 / 288 | GET de IDs + sync por capacidade |
|---|---:|---:|---:|
| T1 prefill 2 043 | 20 814 / 8 111 | 59 235 / 21 072 | 2 241 |
| T1 decode | 8 048 / 6 774 | 24 141 / 20 322 | 2 772 |
| T2 call de 5 | 381 / 313 | 1 143 / 939 | 35 |
| T2 call de 148, tile 1 | 579 / 569 | 1 734 / 1 707 | 35 |
| tile 2 | 308 / 300 | 924 / 900 | 35 |
| tile 3 | 512 / 493 | 1 533 / 1 479 | 35 |
| tile 4 | 527 / 514 | 1 581 / 1 542 | 35 |
| tile 5 | 1 123 / 1 049 | 3 369 / 3 141 | 36 |
| T2 prefill inteiro | 3 430 / 3 238 | 10 284 / 9 708 | 211 |
| T2 primeiro decode | 109 / 92 | 327 / 276 | 36 |
| T2 decode inteiro | 4 706 / 3 987 | 14 115 / 11 961 | 1 656 |
| T2 até ao primeiro conteúdo final | 7 930 / 7 079 | 23 781 / 21 231 | 1 795 |
| T2 até à última saída | 8 136 / 7 225 | 24 399 / 21 669 | 1 867 |

Até ao primeiro conteúdo final, os três papéis a 288 enviam 93 525 840 000 B
em runs unitários e 52 876 800 B em runs duplos. A 161 são 104 748 940 800 B
e 79 315 200 B, respetivamente. No decode a 288 os 52 704 950 400 B são
todos unitários. A 161 são 62 183 116 800 B unitários mais 26 438 400 B
duplos. O prefill T1, que começa com o banco vazio, inclui runs de até oito.
O recibo discrimina, por recorte, o histograma idêntico de gate, up e down,
bytes, chamadas ao mapa e sítios sem faltas. [Resultados completos](result.json)

## Identificação e limites

O header do ik inicia a fila de classe zero com os índices físicos 0 a K−1.
Os slots livres aparecem primeiro nessa ordem. Nos hits só muda a posição
na fila da classe. Nas faltas, percorre os experts únicos por ID crescente
e reutiliza o índice da vítima. A primeira cabeça elegível da classe com
maior score vence; em empate, a classe de índice inferior prevalece.
Dado o banco inicialmente vazio, a sequência completa de quartetos e o
relógio de cada camada, este procedimento determina cada índice de destino
por indução. O replay por chaves e o replay por listas de índices coincidem
em todas as emissões (expert, slot), no mapa inteiro após cada sítio e
nos relógios. Os 6 880 censos de hits/fills/evictions coincidem com o
estudo anterior em cada capacidade. A ponte de 161 tem um controlo nativo
para esses censos. A 288, os endereços calculados são índices do banco
hipotético. Identificar os destinos no fork físico requer observar o grupo
alocado, o seu estado inicial e as rotas desse processo. [Header pinado](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama-moe-cache-policy.h#L92-L121) · [Seleção e publicação](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama-moe-cache-policy.h#L263-L312) · [Controlo anterior](../../natural_link/classlru/two_steps/README.md)

O hook share=0 lê os IDs escolhidos no dispositivo e sincroniza o backend.
Mesmo sem faltas, envia no fim um mapa I32 de 128 entradas (512 B). Havendo
faltas, percorre pela ordem gate, up, down; em cada matriz só junta experts
com IDs e slots consecutivos no mesmo sentido dentro desse sítio. O código
prossegue para o SET do mapa sem sincronização explícita entre os SET de
pesos. Os waits efetivos do driver, scheduler e consumidores, a residência
das páginas, a utilização do enlace e o tempo de cliente exigem medição.
[Ordem dos papéis](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama-moe-cache.cpp#L22-L34) · [Dispatcher de cópias](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama-moe-cache.cpp#L765-L796)

## Reprodução

O protocolo foi congelado em `107d805f`. R01 conservou a falha da validação
que procurava cada tile no compacto anterior. A partir de `079229fe` o
revisor abre o recibo integral autenticado da parte 135. R02 nos originais
e R03 nas partes 97, 106 e 135 produziram ficheiros byte a byte idênticos.
O recibo tem SHA-256 `d5a03811f9a92eae1745306a61ea71530b53b5688de35bae750c83d23d4521d4`.
As 13 760 linhas privadas com preenchimentos e runs por sítio e por
capacidade têm SHA-256 `6a19cce1d1d4cd6bb1038a5b871a6679730494c9fdb7f8de0dc3358d366dfacd`.
Sem GPU, compilação ou modelo. [Protocolo](protocol.md)

```sh
python3 -m pytest -q test_score.py
nice -n 18 python3 -IB score.py --ik "$IK" --previous "$PREVIOUS_RECEIPT" \
  --p97 "$P97" --p106 "$P106" --new-output "$NOVO"
cmp result.json "$NOVO/receipt.json"
```
