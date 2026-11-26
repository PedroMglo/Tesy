# Banco CUDA do 120B nos dois cortes C110

**GO para a prova com o callback desligado.** MEDIDO no portátil e REPRODUZIDO a partir do arquivo. Mudar o banco de 161 para 288 slots preservou os 597 quartetos de experts ordenados e os 402 176 padrões F32. Mudaram 2 143 índices de slot para o mesmo expert e rank. No primeiro passo depois do prefill, 11 faltas passaram a hits. O caso usa 16 IDs fornecidos e, em seguida, o token 976 fornecido. Os máximos únicos nas duas posições foram 3659 e 3992. [Protocolo anterior aos forwards](protocol.md) · [Resultados por braço](physical-pair.json)

| Banco e fase | Reposições | Hits | Matrizes RAM→GPU, B | Leituras do scope no NVMe, B | Intervalo entre ACKs, s |
|---|---:|---:|---:|---:|---:|
| 288, prefill | 1 116 | 0 | 14 752 627 200 | 39 229 030 400 | 21,242 |
| 161, prefill | 1 116 | 0 | 14 752 627 200 | 39 437 164 544 | 19,575 |
| 288, token fornecido | 128 | 16 | 1 692 057 600 | 7 328 997 376 | 4,548 |
| 161, token fornecido | 139 | 5 | 1 837 468 800 | 7 017 160 704 | 4,170 |

Os braços usaram um processo cada, na ordem 288 e 161, com GGUF original no NVMe interno, contexto 8192, ub32, oito threads e GPU SM89. O cgroup E10 tinha 9,5 GiB de `memory.high`, 10 GiB de máximo e zero swap. O pico global de VRAM amostrado foi 6 208 e 4 608 MiB, respetivamente. Os dois processos terminaram e a VRAM voltou aos 2 MiB de entrada. O ciclo completo do filho com observação durou 28,744 e 27,172 s. Os intervalos entre o ACK do token fornecido e o ACK após libertar recursos foram 0,542 e 0,578 s. A energia integrada ficou DESCONHECIDA.

Em cada braço, as 216 multiplicações por experts foram submetidas à GPU. As 216 somas de bias foram submetidas à CPU com o duplicado mapeado do GGUF. A revisão autenticou os bytes e a ordem de cada consumidor. As referências C110, stock e ik CPU reproduzem os dois IDs greedy. Os vetores completos diferem das três referências. A igualdade bit a bit cobre a troca de tamanho entre estes dois bancos no mesmo backend instrumentado. As linhas comparam duas distribuições completas de logits nesses cortes. A equivalência noutras entradas ou em sampling continua por demonstrar.

**DIAGNÓSTICO do armazenamento.** Mesmo no braço que poupou 145 411 200 B de upload, o scope leu mais bytes do NVMe naquela fase. O scope registou 59 119 e 80 746 eventos `memory.high` durante os dois prefills, com 6 743 046 e 9 513 012 refaults de páginas de ficheiro. O JSON guarda em separado os pedidos de cópia, as leituras atribuídas ao PID e ao cgroup e os setores lidos pelo namespace inteiro. O kernel pode servir dados de outros tensores, repetir leituras ou antecipar páginas. Os contadores agregados não localizam os ficheiros ou as dependências responsáveis. Uma execução por configuração, o callback, a telemetria e o estado de page cache impedem atribuir a diferença de segundos à capacidade. Este ensaio tem zero pedidos HTTP. O tempo até ao primeiro conteúdo final e o decode nominal continuam por medir nesta receita.

## Reproduzir sem modelo

O commit físico do Tesy é `69ca7a9f7fd9e7a54cb29cb00fcf7c607f9aefb8`, árvore `ce8116399015833d0f8ad08c521ac793c1f8aab6`. O fork ik é `7a5d90009b7ae55d3239cdd33244977c4eb10ff6`. Os dois arranques físicos antecedem este revisor. Depois do reinício, a cópia temporária do revisor anterior ficou indisponível. Este revisor relê os recibos originais, os journals, os logits de referência e as cópias por braço com o avaliador do commit físico. O arquivo contém 43 ficheiros e 6 677 095 B. [Manifesto público](../../../private_archive/part-141.json) · [Código da reanálise](review.py)

```sh
python3 -IB research/qualification-retake/private_archive/verify.py \
  "$TESY_PRIVATE_ARCHIVE" research/qualification-retake/private_archive/part-141.json
python3 -IB research/qualification-retake/ik_mapped_experts/hybrid/full_parity/review.py \
  --family "$TESY_PRIVATE_ARCHIVE/part-141/tesy-ik-e10-full-parity-20261126-r01" \
  --plan "$TESY_PRIVATE_ARCHIVE/part-138/tesy-ik-capacity-inventory-20261126-r01/plan.tsv" \
  --c110-parent "$C110_RESULTS" --stock-file "$STOCK_LOGITS" \
  --cpu-d0 "$IK_CPU_D0" --cpu-d1 "$IK_CPU_D1" --new-output-dir "$NOVO"
```
