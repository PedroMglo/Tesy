# Quanto pode a escolha de vítimas poupar neste prefill?

**Na própria R02, nem a escolha perfeita de vítimas basta com a agenda serial a 4,5 GB/s úteis e os dois preços anteriores de decode.** Com o banco fixo das 353 vítimas de T1 e 40 slots por camada, o mínimo é **734 leituras** mesmo deixando livres todos os conjuntos de saída. Aos preços de pack das ordens RP e PR cabem apenas **674 e 663 leituras**, respetivamente. As 734 leituras custariam 9 702 892 800 B de payload e ainda excederiam o orçamento em 174 e 206 ms. [Recibo dos dois replays](evidence/receipt.json) · [Pré-registo](protocol.md)

Para preservar os membros do *carry* — a política que transporta o estado primário produzido pelo prefill para o primeiro decode — nos dois retornos, o mínimo sobe para **787 leituras**, ou 10 403 510 400 B. Com as mesmas obrigações nos retornos físicos de R0, a R02 deu **793**. O segundo número coincide com o da parte 40 por cálculo independente. Entre as duas trajetórias desta R02, há 14 substituições de membro após o retorno de 5 tokens e 19 à entrada de decode; a identidade dos membros explica por que o mesmo traço de procura pode dar mínimos diferentes. [Oráculo histórico da parte 40](../../../../../tile_boundary_floor/cuts.md) · [Reconstrução do carry R02](../../replay/README.md)

| Conjuntos de residentes exigidos | R0, CPU + CUDA | Carry, CPU + CUDA |
|---|---:|---:|
| Todos os cortes entre tiles e os dois retornos | 621 + 364 = 985 | 600 + 358 = 958 |
| Retorno de 5 e entrada de decode, quatro cortes internos livres | 505 + 288 = **793** | 499 + 288 = **787** |
| Retorno de 5 fixo, entrada de decode livre | 485 + 269 = 754 | 478 + 268 = 746 |
| Só entrada de decode fixa | 490 + 286 = 776 | 491 + 287 = 778 |
| Sem conjuntos de saída prescritos | 467 + 267 = **734** | 467 + 267 = **734** |

Preservando os membros do carry no retorno de 5, o custo mínimo conjunto sobe de 746 para 787 ao exigir a sua entrada de decode (**+41 leituras**). Com o primeiro retorno livre, sobe de 734 para 778 (**+44**). A reposição foi incluída na otimização sobre toda a sequência, acrescentando os 40 membros finais como última wave de cada camada. A diferença entre mínimos não é o custo de uma rotina de restauração sobre uma agenda escolhida separadamente.

### Banda e orçamento com os membros do carry

| Cenário aplicado às 787 leituras | Pack após GGUF (RP) | Pack antes de GGUF (PR) |
|---|---:|---:|
| Preço condicional do decode conservado | 7,084608 s | 7,116859 s |
| Banda útil mínima com as lacunas seriais observadas | **5,247 GB/s** | **5,334 GB/s** |
| Margem a 4,5 GB/s, lacunas seriais | **−329 ms** | **−362 ms** |
| Banda mínima com o pipeline otimista de duas tiles | 3,750 GB/s | 3,794 GB/s |
| Margem a 4,5 GB/s, pipeline otimista | **+462 ms** | **+430 ms** |

O cálculo serial conserva 1,151151 s de lacunas drenadas e o de duas tiles conserva 0,359485 s expostos. A configuração anterior de carry pedia 1 058 leituras de disco no prefill. Reduzi-las para o mínimo 787 compraria 271 payloads, mas a agenda serial precisaria de poupar pelo menos 384 ou 395. Com o pipeline mais favorável cabem 944 ou 933 leituras. Nas 16 combinações pré-registadas de cortes do carry, 13 têm mínimo ≤933 e três não chegam lá. Preservar todos os cortes dá 958, acima do limite. **A escolha de vítimas volta a ter margem como intervenção combinada** se a liberação de trabalho entre tiles, a banda efetiva ou o preço do decode mudarem o suficiente para acomodar a agenda realizável. [Fronteira do prefill e limites da sobreposição](../README.md)

### O que o oráculo conserva

O PFJ1 da parte 63 forneceu as posições 2 044–2 196, chamadas de 5 e 148, as cinco tiles 32/32/32/32/20, última camada podada nas primeiras quatro tiles e todos os conjuntos de experts pedidos em simultâneo. As seis tiles contribuíram 35, 53, 36, 52, 52 e 81 grupos de procura não vazios. O oráculo conhece as waves futuras. Escolhe sobreviventes dentro dos 40 slots de cada camada, cobra cada admissão de disco e permite reintroduzir gratuitamente identidades do banco desde que caibam enquanto são usadas. Concede permutas físicas gratuitas e dispensa parking concreto, preloads obrigatórios, gerações, idades, calor, cópias e sincronização. Os retornos das chamadas continuam a existir mesmo quando não se exige um conjunto específico de residentes.

Os sete conjuntos R0 foram derivados de eventos físicos com fila e LOADING vazios. Os sete do carry foram **reconstruídos** com o seletor selado, incluindo a ordem das rotas, o digest das posições de slots, os totais por tier e a população completa das 1 656 callbacks de decode do plano arquivado. Os hashes dos membros constam no recibo. O estado completo do carry no primeiro decode não tem snapshot físico independente. Restituir membros dá liberdade para escolher slots, gerações, calor e idades diferentes. Esses valores podem mudar as próximas vítimas, os hits do banco e os 797 jobs usados no preço de decode. Nem a margem positiva sob pipeline nem o mínimo de leituras demonstra uma política causal, igualdade dos resultados numéricos ou ganho de produto.

### Reprodução offline

Pré-registo `54d3058a`, código `98e63c83`. Três testes cobrem o oráculo pago por enumeração, pins simultâneos e o preço da reposição. Executar na checkout limpa de medição com o ambiente Python do Tesy. O import do helper histórico usa NumPy, disponível nesse ambiente. O Python de sistema não o tinha no teste de preparação. R01 consumiu 1,12 s de parede e 122 200 KiB de RSS máxima. R02 consumiu 0,98 s e 122 184 KiB. Os recibos de 17 743 B foram idênticos, SHA-256 `991fb5d4804b207e96e190101a0a0d68cad3a46cc1abb766fee47567fab39e9b`. A parte 70 guarda os dois recibos deste cálculo e os restantes registos da janela em 7 ficheiros, 114 292 B, com manifesto SHA-256 `8e5f2ea585be7bbdb46e1d3d30d2978d9445217f848233f6c774efc564056723`. O programa só lê os dados selados nas partes 63 e 65 e o compacto anterior que autentica os preços da parte 66. [Implementação](screen.py) · [Testes](test_screen.py)

```sh
U=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/prefill_frontier/oracle
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$TESY_VENV/bin/python" -IB "$U/test_screen.py"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$TESY_VENV/bin/python" -IB "$U/screen.py" \
  --archive "$ARCHIVE" --new-output-dir "$NEW"
sha256sum "$NEW/receipt.json"
```
