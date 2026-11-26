# Preparar o primário antes do primeiro decode

**Com o serviço original de C294, a preparação permitida nas 40 posições de cada camada admite o alvo nominal, mas o código ultrapassa o orçamento comum nas duas réplicas.** No nominal seriam necessárias, no mínimo, 252 ou 261 escolhas perfeitas antes do primeiro decode. Em código, até o melhor resultado ultrapassa 5,333333 s em 6,61 ou 11,99 ms. Essa diferença pertence ao modelo temporal histórico: é sensível à escala de READ, à sobreposição e ao estado inicial. Não permite inferir uma diferença material na conversa. À escala 0,8 os quatro braços cabem. Este último resultado abre **apenas a avaliação de uma seleção causal em dados independentes**, condicionada a demonstrar o serviço mais curto e a pagar a preparação. M3 PARTIAL e M4 NOT_MET. [Pré-registo](protocol.md) · [Recibo integral em JSON compacto](evidence/receipt.json)

O número na tabela é o menor conjunto de chaves (camada, expert) que satisfaz o limite. «Falha» indica que nenhum conjunto elegível consegue atingir o alvo. O universo livre concede qualquer chave e lugar. O universo por camada só admite as vagas reais ou os lugares de residentes que o futuro decode nunca pedirá, e exige uma utilização demonstrada no prefixo ou na chamada incremental. O universo estrito exige residência em P ou uma publicação no incremento. As colunas de percentagem dão a fração de parede de READ retirada dos máximos por grupo no universo por camada; para o código a 1× mostram o melhor ponto atingível.

| Braço | Livre 1× / 0,8× | Por camada 1× / 0,8× | READ retirado 1× / 0,8× | Estrito 1× / 0,8× |
|---|---:|---:|---:|---:|
| Nominal 2 | 209 / 92 | 252 / 117 | 36,03% / 20,11% | Falha / 132 |
| Nominal 3 | 216 / 99 | 261 / 127 | 37,02% / 21,34% | Falha / 146 |
| Código 2 | 356 / 231 | Falha / 269 | 48,52% / 35,80% | Falha / 283 |
| Código 3 | 361 / 237 | Falha / 272 | 48,61% / 36,01% | Falha / 283 |

O replay confere os quatro estados I, os 32 × 36 grupos e os ranks oficiais contra o WRT. O estado real deixa 647 lugares utilizáveis no nominal e 634 em código, contando as 29 vagas originais em cada braço. As restrições por camada e de origem deixam 433 das 779 faltas obrigatórias elegíveis no nominal e 612 das 928 em código. A programação dinâmica enumera subconjuntos de no máximo quatro faltas simultâneas, recalcula a última leitura necessária do grupo e combina os ganhos dentro das capacidades de cada camada. O recibo guarda as listas concretas, prova que o custo ótimo com uma escolha a menos excede o alvo e reconfirma a duração diretamente a partir daquelas chaves. Nos casos impossíveis, o testemunho usa a menor cardinalidade que alcança o ganho máximo: 436/440 no código por camada a 1×. [Piso anterior e hipóteses do relógio](../primary_backing/README.md) · [Oráculo](solver.py)

| Braço por camada | Payload das escolhas mínimas a 0,8× | Origem: publicação incremental / residente P / apenas rota pré-P | Folga no menor conjunto a 0,8× | Folga máxima a 0,8× |
|---|---:|---:|---:|---:|
| Nominal 2 | 1,440 GiB | 32 / 36 / 49 | 4,63 ms | 975,86 ms |
| Nominal 3 | 1,564 GiB | 33 / 37 / 57 | 4,54 ms | 912,59 ms |
| Código 2 | 3,312 GiB | 156 / 65 / 48 | 1,67 ms | 697,96 ms |
| Código 3 | 3,349 GiB | 170 / 60 / 42 | 1,28 ms | 691,27 ms |

Cada chave ocupa 13 219 200 B no seu tier. O payload da tabela é também o mínimo a entregar se todas as escolhas tiverem de ser materializadas integralmente num novo destino. Reter um expert desde uma publicação anterior pode evitar a releitura, mas ocupa um lugar desde essa publicação. Uma rota pré-P comprova utilização anterior; manter disponíveis os respetivos bytes é trabalho adicional. Os tempos incluem o restante fixo de C295, dão custo zero a essas operações na entrada e concedem retenção ilimitada depois de I. Assim, as folgas são orçamentos no relógio do decode. Preparação após a chegada do pedido entra também no prefill e no primeiro conteúdo final. Uma regra causal deverá manter paridade de rotas/logits e cobrar a deslocação, cópias e residentes perdidos desde o momento da escolha. Nenhum testemunho dirige uma política operacional. [Ablação anterior de L2 com cópias](../l2_decode_entry/README.md)

## Reprodução

Protocolo `9693d295`, medição `d6beeeb2b82a76dfe996b24347318c47f547be22`, árvore `3ca67ec0d596b342c75bb3650487c24a49bef0e8`. Nove testes sem modelo incluem 150 comparações exatas com força bruta. R01/R02 consumiram 3,01/2,78 s de parede e 107 592/106 584 KiB de RSS máxima. Os dois recibos privados têm 589 864 B e o mesmo SHA-256 `030873685b0212cd5835f547325367926265167e17c7554686a00ca08f6ac75a`. O JSON publicado conserva todos os campos e testemunhos em 88 295 B; SHA-256 `73e7c83e29fc59b30e26193273334f3aecfb5672941ded22a443cfb15a863075`. Zero pesos ou GPU.

```sh
python3 -B -m unittest discover -s research/qualification-retake/primary_entry_timing
LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  timeout 120 python3 -B research/qualification-retake/primary_entry_timing/screen.py \
  --family "$WRT_FAMILY" --raw-dir "$TESY_C294_RAW" --new-output-dir "$DESTINO_NOVO"
python3 -c 'import json,sys; a,b=map(open,sys.argv[1:]); assert json.load(a)==json.load(b)' \
  "$DESTINO_NOVO/receipt.json" research/qualification-retake/primary_entry_timing/evidence/receipt.json
```
