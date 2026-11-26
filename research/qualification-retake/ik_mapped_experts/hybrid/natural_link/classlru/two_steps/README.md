# O que compra espaço para duas seleções máximas de decode?

**GO para ensaiar primeiro a capacidade de 288 slots reais com ClassLRU,
condicionado ao pico de VRAM do próprio ik.** Face aos 161, este replay
elimina 911 reposições em T2, equivalentes a 12,043 GB, e acrescenta
1 601,065 MiB de reserva CUDA. Até à primeira peça final a taxa útil
necessária cai de **10,483 para 9,358 GB/s**. No decode completo cai de
**7,942 para 6,728 GB/s**. A qualificação de latência continua INCONCLUSIVE.
[Protocolo](protocol.md) · [Resultados](result.json)

| Reposições por recorte | LRU 161 | LRU 288 | ClassLRU 161 | ClassLRU 288 |
|---|---:|---:|---:|---:|
| T1, prefill 2 043 | 21 081 | 11 022 | 20 814 | 8 111 |
| T1, 77 avaliações de decode | 7 959 | 7 117 | 8 048 | 6 774 |
| T2, call de 5 | 451 | 391 | 381 | 313 |
| T2, call de 148 | 3 367 | 3 367 | 3 049 | 2 925 |
| Primeiro decode de T2 | 139 | 124 | 109 | 92 |
| T2, desde a entrada até à primeira peça final | 8 484 | 7 968 | 7 930 | 7 079 |
| T2, 46 avaliações de decode | 4 857 | 4 376 | 4 706 | 3 987 |
| T2, até à última das 47 saídas | 8 675 | 8 134 | 8 136 | 7 225 |
| Total T1 + T2 | 37 715 | 26 273 | 36 998 | 22 110 |

As 74 278 linhas de T1 e 7 012 de T2 deram 32 169 e 10 450 procuras
distintas por sítio. Com ClassLRU 288, T1 custaria 196,768 GB e T2
95,509 GB de payload H2D. Juntos poupam 196,807 GB face a 161. O primeiro
conteúdo final corresponde à amostra 45 após a call 46 de T2. Nas cinco
tiles de 148, ClassLRU 288 carrega 569, 300, 493, 514 e 1 049 vezes. Com
LRU 288 continuam a faltar todas as 3 367 chaves dessa chamada.

**Origem dos hits no decode de T2.** Entre os 719 fills evitados por
ClassLRU 288, a última procura da mesma chave ocorreu no passo de decode
imediatamente anterior em 249 casos, pelo menos dois passos antes em 437,
durante o prefill T2 em 32 e em T1 num caso. O banco maior manteve todos
os hits do menor nesta trajetória. No LRU foram evitados 481 fills. Em
462 casos a chave tinha sido pedida pelo menos dois passos de decode antes,
e em 19 provinha do prefill. O LRU 161 aqui já cobre as chaves pedidas
no passo imediatamente anterior. As categorias medem última procura
autoritativa. A promoção e o tempo de retenção variam com a política.

| Capacidade e política | Até à primeira peça em 10 s | Decode de 47 saídas em 47/6 s |
|---|---:|---:|
| LRU 161 | 11,215 GB/s | 8,196 GB/s |
| LRU 288 | 10,533 GB/s | 7,385 GB/s |
| ClassLRU 161 | 10,483 GB/s | 7,942 GB/s |
| ClassLRU 288 | 9,358 GB/s | 6,728 GB/s |

**Capacidade física.** O seletor do ik soma a guarda e o alinhamento de
cada papel. Com 288 reais, o limiar do pedido é 3 644 MiB para três bancos
de 289 linhas. O payload com guarda ocupa 3 820 348 800 B. O alocador real
do backend CUDA ainda acrescenta a cauda da última linha quantizada e alinha
cada banco a 128 B, totalizando **3 820 349 184 B**. Em 161 reais os valores
são 2 141 510 400 B e 2 141 510 784 B. O mínimo inteiro é 2 043 MiB, e o
controlo histórico pediu 2 048 MiB. Uma camada pode precisar de 128 experts
numa tile ub32 e todas as 36 podem pedir 144 chaves num passo unitário.

A maior observação stock do ensaio natural com 161 foi **4 386 MiB**.
Esse T1 expirou aos 180 s antes de uma resposta, pelo que o pico é
amostrado e cobre um pedido censurado. Se o resto se mantiver, os 127 slots
adicionais levariam a 5 987,065 MiB. A regra ncmoe do ik seleciona
matrizes/scale e pode deixar os 108 biases na GPU. Colocar aí todos os
159 252 480 B elevaria a projeção a **6 138,940 MiB**, deixando **1 537,060
MiB** até ao guard histórico de 7 676 MiB dos 8 188 MiB reportados. Esta
margem condiciona a escolha. O teste de capacidade do ik terá de confirmar
os dispositivos dos biases, os grupos, a alocação, workspace, contexto,
pico e política contemporânea. [Experiência stock](../../../../../stock_nominal_conversation/README.md) · [Inventário dos biases](../../../../header_index/README.md)

**Método e reprodução.** As filas lógicas respeitam a ordem de hits, o
conjunto protegido, os fills ordenados e o desempate de vítimas do pin.
Para ClassLRU a frequência usa valores binary32, exp2f e log2f, com o
relógio da largura real de cada camada. O código C++ selado aceita até
161 na sua CLI. A ponte comparou hits, fills e evictions em todos os
6 880 sítios contra os dois recibos nativos de 161. Os 288 são
TRACE_DERIVED, com estado inicial vazio antes de T1 e sem as rotas de
sonda anteriores ao primeiro POST. A 288 não houve compilação, execução
do planner nativo, medição de tráfego, preço de página ou confirmação de
rotas próprias do fork. [Planners de controlo](../README.md) · [Implementação](score.py)

R01 preserva as contas de rotas, mas usou como referência o pedido curto
stock de 4 348 MiB e omitiu os 384 B de padding CUDA no total de cada
geometria. R02 corrigiu estas duas rubricas ao abrigo do protocolo
ca96bd6c. Em ecbd665a os originais e as cópias das partes 12, 97 e 106
produziram o mesmo SHA-256
`149254cbe4de3cecaf6ecd6dc9a07813d46fdfe6aa96b5bc24d81bc59e545b96`.

```sh
python3 -m pytest -q test_score.py
nice -n 18 python3 -IB score.py --p97 "$P97" --p106 "$P106" \
  --ik "$IK" --policy "$STOCK_NOMINAL_C55/resource-policy.json" --new-output "$NOVO"
```
