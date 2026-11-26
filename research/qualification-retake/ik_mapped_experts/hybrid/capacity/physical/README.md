# Capacidade do banco híbrido do ik no portátil

**R02 qualificou a carga do 120B MXFP4 e a criação do contexto de 8 192 posições com um grupo ClassLRU de 36 camadas, 288 slots reais e uma guarda.** O supervisor mediu 6 150 MiB de VRAM no corte do contexto e 2 MiB após o exit. Ficaram 1 526 MiB até ao limite preventivo de 7 676 MiB nessa observação. A execução terminou com KV vazio e zero submissões de grafo. A utilização de uma das cópias de bias pelo operador, a memória durante inferência e o preço por token exigem um forward. [Protocolo da carga](../protocol.md) · [Critério da revisão independente](protocol.md)

## O que falhou na R01 e o que a R02 acrescentou

A primeira procura por nome devolveu 687 tensores em cada processo. As 217 vistas CPU cobrem exatamente os intervalos do GGUF de 108 matrizes MXFP4 (60 914 073 600 B), dos 108 biases (159 252 480 B) e do embedding (615 329 280 B). As restantes 470 primeiras ocorrências estavam em CUDA, incluindo os dois tensores de saída. O revisor confirmou a presença das vistas nas VMAs do inode original nos cortes L e C e a sua libertação no corte F.

Na **R01, FAIL_PRESERVED**, o executor observou para cada bias um SET com toda a região de origem e uma cópia H2D com destino distinto da vista CPU. A API de pesquisa por nome continuou a devolver CPU. Faltou a identidade do segundo tensor no contexto que ligasse esse destino ao bias CUDA. Na reabertura, o verificador do próprio freeze voltou a falhar em `bias/output placement`. O processo tinha já passado os cortes E/L/C/F e terminado com código zero. [Recibo R01](r01.json)

Na **R02, PASS_IK_REAL_CAPACITY_NO_FORWARD**, o observador enumerou 216 instâncias do contexto para os mesmos 108 nomes. Conferiu o endereço da ocorrência CPU contra o intervalo do mmap e o da ocorrência CUDA contra a totalidade dos bytes enviados para cada bias. A prova independe da ordem da enumeração. Nos dois braços os 578 SET e 578 pedidos de cópia cobriram 1 844 921 088 B H2D na carga, incluindo 159 252 480 B de biases e zero bytes das 108 matrizes. O contexto pediu ainda 4 424 329 266 B de memset, operação no dispositivo. Cada executor bloqueava a submissão de grafo e terminou com zero forwards. [Recibo R02](r02.json) · [Grade das instâncias](../grade.py)

## Memória e I/O

O breakdown devolvido pelo ik após a criação do contexto foi idêntico nas duas execuções.

| Rubrica em bytes | CUDA0 | Host |
|---|---:|---:|
| Modelo | 1 844 948 992 | 62 758 971 648 |
| Contexto, já com o banco de experts e KV | 4 424 328 960 | 822 848 |
| Compute reservado | 71 156 352 | 2 466 208 |

O pedido para o banco foi 3 644 MiB, com 289 linhas físicas por papel. O log confirma 576 MiB de KV CUDA, com 8 192 células reservadas e nenhuma usada. A API de memória reportou 1 791 033 344 B livres de um total de 8 238 792 704 B no dispositivo. Esta contabilidade do backend e o uso global por NVML têm universos próprios. O valor de modelo Host inclui endereçamento no ficheiro mapeado. O custo de RAM cobrado ao scope e o tráfego de armazenamento são observações separadas.

| Medida do supervisor | R01, falha de colocação | R02, qualificada |
|---|---:|---:|
| Inventário C118 (61 amostras cada) | 60,181 s | 60,155 s |
| ACK de entrada → modelo carregado | 1,882 s | 1,219 s |
| ACK do modelo → contexto pronto | 0,301 s | 0,336 s |
| ACK do contexto → objetos do backend libertados | 0,404 s | 0,341 s |
| Arranque até ao exit do filho | 3,035 s | 2,355 s |
| VRAM global em E / L / C / F / exit (MiB) | 2 / 1 862 / 6 150 / 102 / 2 | 2 / 1 862 / 6 150 / 102 / 2 |
| Pico de memória do cgroup (B) | 1 349 709 824 | 371 838 976 |
| Leitura global no namespace NVMe (setores × 512 B) | 1 008 771 072 B | 23 150 592 B |
| Leitura cobrada ao cgroup em 259:0 | 1 008 361 472 B | 23 150 592 B |
| Swap / OOM / eventos memory.high | 0 / 0 / 0 | 0 / 0 / 0 |

O relógio dos ACK inclui amostragem e coordenação do supervisor. Os mesmos 6 150 MiB foram o máximo global observado em cada família, com libertação da VRAM residual após o exit. Havia alimentação AC em performance, com MemoryHigh de 9,5 GiB, MemoryMax de 10 GiB e swap desativado. Cada sessão teve uma C55 e uma C118 próprias. Os dois pedidos de carga ocorreram em momentos distintos, sem controlo do estado da page cache. A diferença de GB lidos e o tempo de carga não isolam um efeito da sonda. O namespace inclui todos os utilizadores. O contador cgroup agrega o processo e o supervisor. Nenhum dos dois identifica os setores de uma matriz individual.

## Reprodução

O revisor reabre o plano, o ELF do cliente, o preflight, as sete saídas privadas de cada processo e os respetivos hashes antes de invocar a grade da checkout congelada daquele braço. Recalcula a cobertura dos uploads, a vida das vistas por inode/offset e a política de recursos na data da C118. Os dois caminhos da primeira versão do revisor tinham dependido de um helper que na R01 existia apenas inline. Esses diagnósticos offline foram preservados com SHA `4ada1d0e7285c7734f49b57d3a4b975e173a702b55e0c5c76a446b8851441be3`. A versão corrigida usa a mesma verificação de cobertura extraída na R02 para o diagnóstico e reaplica a grade própria de cada campanha para a decisão. [Revisor](review.py) · [Testes](test_review.py)

| Identidade | SHA-256 do braço | SHA-256 da revisão |
|---|---|---|
| R01 | `35abb80c85446c4754b6602fb258d2a0841021e8524290ab48d2ecd4ec9bbd00` | `c89702d6707b3f2ce268bf6fa5860e343a34ab6a87505b11c7f4f5601ed103a1` |
| R02 | `8d926cd1661e4f1af246ecb03426f9a24b7928c13934f51125ae08e9d2d7f73c` | `f66eb36d4fedde7c9aab2783a7dcabc53b631b3848cb60a5e13fd9fc56365577` |

Cada um dos dois resultados foi reproduzido byte a byte a partir dos originais e dos raws preservados nas partes 138–140. A invocação abaixo usa a parte própria de cada braço para a família, a C55 e a preparação. Para R01, o cliente e o inventário estão na parte 138. Para R02, o cliente está na parte 140 e o inventário continua na 138. `FREEZE` aponta à checkout da campanha (`ac8fcbfd` ou `455d7ceb`) e `NEW` é um destino exclusivo. Os ficheiros de pesos não são consultados. [Manifesto da parte 138](../../../../private_archive/part-138.json) · [Parte 139](../../../../private_archive/part-139.json) · [Parte 140](../../../../private_archive/part-140.json)

```sh
python3 -IB review.py --family "$FAMILY" --family-sha256 "$FAMILY_SHA" \
  --freeze "$FREEZE" --prepared "$PREPARED" --client "$BUILD" \
  --inputs "$INVENTORY" --c55 "$C55" --new-output-dir "$NEW"
pytest -q test_review.py
```
