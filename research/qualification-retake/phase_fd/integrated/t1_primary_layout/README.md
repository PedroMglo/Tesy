# O layout continua a valer a pena depois dos acertos da cache?

**MEDIDO no portátil. As duas melhorias acumularam-se na entrega dos pesos em RAM.** Comparámos LRU e expulsão prioritária dos experts com cópia no mesmo banco em RAM, cada uma com o GGUF original e o pack contíguo. Nas quatro waves do segundo turno, o tempo mediano total passou de 123,683 para 45,077 ms no primeiro processo e de 117,076 para 44,163 ms no segundo. A redução mediana emparelhada foi **63,46% e 62,61%**. Com o pack já ativo, a nova política ainda retirou **20,76% e 20,00%**. Com a nova política ativa, o pack ainda retirou **52,67% e 50,72%**. Os três contrastes tiveram sinal favorável nos oito blocos. **GO para medir a entrega aos destinos reais CPU e CUDA.** A conversa natural continua em M3 PARTIAL e M4 NOT_MET. [Pré-registo da medição](physical.md) · [Recibo por processo e bloco](evidence/physical.json)

| Processo e bloco | LRU + GGUF (ms) | LRU + pack (ms) | Nova política + GGUF (ms) | Nova política + pack (ms) |
|---|---:|---:|---:|---:|
| P1, 1 | 123,971 | 56,654 | 94,873 | 43,850 |
| P1, 2 | 122,551 | 57,440 | 95,929 | 45,549 |
| P1, 3 | 124,226 | 56,338 | 94,558 | 44,605 |
| P1, 4 | 123,396 | 55,554 | 95,229 | 46,246 |
| P2, 1 | **350,646** | 56,100 | 89,713 | 46,012 |
| P2, 2 | 115,576 | 56,062 | 88,101 | 43,547 |
| P2, 3 | 116,309 | 54,163 | 90,780 | 44,596 |
| P2, 4 | 117,843 | 56,071 | 90,299 | 43,730 |

O valor de 350,646 ms está incluído. Nos três blocos seguintes de P2, os ganhos combinados foram 62,322%, 61,657% e 62,891%. As percentagens acima são medianas de diferenças relativas dentro de cada bloco. Somar percentagens isoladas contaria duas vezes parte do custo de leituras que a outra intervenção retira. Com o banco e o layout originais da fixture, a nova política sozinha poupava 23,15%/23,57%. Sobre o pack, a sua contribuição marginal continua positiva. Este controlo usa LRU com o mesmo banco em todos os braços. O controlo de produto R0 trace-OFF continua a ser o da conversa de dois turnos. [Comparação de R0 e estados de fronteira](../t1_primary_victim/README.md)

## Trabalho e denominador

O plano partiu do próprio journal do T2 e selou as primeiras waves de CPU e CUDA da call148 e do decode com conjuntos de faltas diferentes entre políticas, aceitando qualquer sinal. As quatro escolhidas tiveram uma leitura de disco a menos com a nova política. Em todas as waves não vazias da call148, 32 de 274 diferiram. No decode, 151 de 1 656 diferiram e em duas a nova política piorou. Os quatro exemplos estudam o mecanismo em pontos de divergência. Uma estimativa do pedido completo exige incluir também as restantes waves, preparação do banco e reconstituição à entrada de decode. [Método de seleção e cobertura integral](protocol.md) · [Contagens do plano](plan-receipt.json)

| Wave | Consumidores | LRU, disco / RAM / primário | Nova política, disco / RAM / primário |
|---|---:|---:|---:|
| Prefill CPU | 12 | 11 / 1 / 0 | 10 / 1 / 1 |
| Prefill CUDA | 9 | 3 / 0 / 6 | 2 / 3 / 4 |
| Decode CPU | 4 | 3 / 0 / 1 | 2 / 0 / 2 |
| Decode CUDA | 4 | 1 / 0 / 3 | 0 / 0 / 4 |

Em ambos os layouts, o FD de medição estava no NVMe interno. O pack da fixture preserva os bytes originais e compacta as lacunas entre os 29 registos escolhidos. Essa compactação pode favorecer a localidade do disco. O pack USB serviu apenas para preparar a fatia interna, com tamanho de 383 434 752 B e SHA-256 `fb6f26e367b3d9e5b5b18aab3e25c7f3c6d273e4e2e18947b9f2a50356ddaf34`. Comparámos as 87 componentes com o índice integral e o GGUF. Cada processo verificou também 1 740 digests nas entregas de controlo e cronometradas.

Os bytes devolvidos pelo FD das quatro waves numa célula foram 238 178 304 em A, 237 993 984 em B, 185 262 080 em C e 185 106 432 em D. Cada processo contabilizou 4 232 704 000 B nas cinco passagens pelas quatro células, incluindo aquecimento. O relógio inicia no despacho dos trabalhos e termina quando os quatro workers entregam os pesos em buffers CPU. Inclui as cópias dos hits em RAM e do staging para esses destinos. As tabelas dizem CPU ou CUDA conforme o destino previsto no grafo original. Neste ensaio os dois receberam dados em RAM. GPU, kernels FFN, publicação no manager, estado KV e tempo de cliente não foram medidos. A diferença de bytes de FD é uma medição do que o leitor pediu e recebeu. Os bytes internos de NAND permanecem desconhecidos.

## Recursos, falhas e reprodução

A admissão C55 recolheu 62 amostras durante 61,018 s com alimentação AC, performance e zero processos de computação GPU. Ambos os scopes usaram 1 GiB de RAM e MemorySwapMax=0. As duas C118 recolheram 61 amostras cada. Os picos do cgroup foram 763 867 136 e 763 498 496 B. Máximos observados de CPU 62,125/56,000 °C, GPU 47,45/42,92 °C e NVMe 36,85/36,85 °C, com 2 MiB reportados pela GPU. Zero forwards e zero cálculo na GPU. A preparação e verificação fora do relógio demoraram 3,074/1,637 s. O segundo processo reutilizou o ficheiro depois de confirmar identidade, tamanho e conteúdo. A energia integrada não foi medida.

Pré-registo do plano em `19fe7685`. Os dois planos iniciais falharam porque o índice C290 designa o tier por GPU. Conservámos a falha. Na correção `a129e386`, as duas confirmações levaram 0,61 s cada e coincidiram byte a byte, SHA-256 privado do plano `761efff70fc046f5810974ab7656fe90f893e3a3a2af8461693103769d7f2b76`. Antes de medir, selámos o protocolo em `462ff342` e a implementação em `0c4c42e1acdfa882febe1264283b5fa94ab61171`, árvore `12174c42f255aea80faf08a2fe891c6032327e10`. A primeira tentativa física parou na verificação do recibo NVML, antes de abrir os pesos. Os dois processos seguintes usaram o mesmo provider qualificado para campanhas CPU, com o mesmo código e critérios. [Falha do plano](plan-failure.json) · [Falha de arranque](evidence/start-failure.json)

O arquivo privado `qualification-20261124-nvme-01/part-44` conserva 22 ficheiros, 248 799 B, com manifesto SHA-256 `acfba2c4abc6230540616b897dab4ac7fd4275482800722e23916eb7bfb913dc`. Os resultados da política causal e do ótimo ficaram na parte 45 e os anteriores sobre volume e coordenação na parte 43. O verificador reproduziu o recibo compacto SHA-256 `571f2f69698e5182de552ade584c73d1e436f3655c19f69055b3cdb3dfd7d383` a partir da cópia arquivada.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_primary_layout
python3 -IB "$unit/review.py" \
  --first "$ARCHIVE/part-44/tesy-layout-combined-physical-20261125-r02" \
  --second "$ARCHIVE/part-44/tesy-layout-combined-physical-20261125-r03" \
  --new-output-dir "$NEW_REPORT"
cmp "$NEW_REPORT/receipt.json" "$unit/evidence/physical.json"
```

Para reproduzir fisicamente, usar a checkout limpa de medição, o plano, o recibo de colocação e os inputs identificados, uma C55 contemporânea e o provider do monitor verificado. Escolher duas novas unidades, duas saídas novas e um nome ainda livre para a fatia interna. Uma execução do comando abaixo faz o primeiro processo. No segundo, manter o mesmo nome de fatia, mudar unidade, saída e o argumento de arm para 2 e acrescentar `--first-dir "$FIRST" --first-sha256 "$FIRST_SHA"`. A sessão C55 deve manter-se dentro da janela de validade.

```sh
systemd-run --user --scope --unit="$UNIT1" -p MemoryHigh=1G -p MemoryMax=1G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=180 env LD_LIBRARY_PATH="$MONITOR" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$TESY_VENV/bin/python" -IB "$unit/bench.py" \
  --arm 1 --commit 0c4c42e1acdfa882febe1264283b5fa94ab61171 --unit "$UNIT1" \
  --plan "$ARCHIVE/part-44/tesy-transport-victims-plan-20261125-r03/plan.json" \
  --model "$GGUF_NVME" --pack "$FULL_PACK_USB" --partial "$NEW_PARTIAL_NVME" \
  --placement "$PLACEMENT" --c55 "$C55" --c55-sha256 "$C55_SHA" --new-output-dir "$FIRST"
```
