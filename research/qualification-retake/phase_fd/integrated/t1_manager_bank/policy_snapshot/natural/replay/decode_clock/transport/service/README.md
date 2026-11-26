# Serviço de leitura dos 46 passos do decode

**MEDIDO.** O pack terminou as barreiras de leitura dos 797 experts **1,333 s e 1,279 s mais cedo** do que o GGUF nos dois pares em ordem inversa. O preço por callback e as hipóteses de SETs e exterior do candidato entram separadamente na comparação com o objetivo de produto. [Resultados e cruzamentos do revisor](../service-result.md)

| Processo / braço | Soma de READ por worker | União das leituras | Despacho até ao drain | Hashes fora do serviço | Monitor | Outras despesas | Travessia de parede |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 R | 7,720 s | 5,587 s | 5,617 s | 4,391 s | 2,098 s | 0,163 s | 12,268 s |
| 1 P | 5,917 s | 4,257 s | 4,284 s | 4,388 s | 1,781 s | 0,141 s | 10,594 s |
| 2 P | 5,985 s | 4,288 s | 4,319 s | 4,369 s | 1,854 s | 0,146 s | 10,688 s |
| 2 R | 7,696 s | 5,567 s | 5,598 s | 4,393 s | 2,194 s | 0,151 s | 12,335 s |

O tempo de parede corresponde ao drain mais autenticação, monitor e despesas restantes. A janela do drain contém os preads. Cada processo verificou 4 782 componentes ao longo das duas travessias, num total de 9 564. Nas duas ordens os 42 166 583 296 B pedidos em O_DIRECT incluíram 42 142 809 600 B de payload. A diferença corresponde ao alinhamento e ao padding. Os quatro contadores de bloco do dispositivo observaram, na sequência R/P/P/R, 20 596 608, 20 582 528, 20 581 728 e 20 596 576 setores de 512 B lidos. São contadores de todo o dispositivo, incluindo entre grupos.

| Processo | C118 | Tempo total com C118 | Pico de RAM no cgroup | Cleanup de FDs, pool e buffers | Máximos CPU / NVMe / GPU | SHA-256 do recibo privado |
|---|---:|---:|---:|---:|---:|---|
| RP | 61 amostras / 60,182 s | 83,41 s | 107 134 976 B | 6,086 ms | 58,25 / 40,85 / 45,61 °C | `1ac4bb4e666b61898cbb655cddb24d771529e71d66515e56862b989434b76e57` |
| PR | 61 amostras / 60,199 s | 83,74 s | 106 627 072 B | 5,435 ms | 57,00 / 40,85 / 45,61 °C | `acd29327feb616f130f9518e67f39d1bc69e692f896352706dd4ed2a13a49e98` |

Houve 26 amostras ativas por processo; o consumo observado de VRAM ficou em 2 MiB. O swap do cgroup foi zero. O NVMe apresentou firmware V3MA101. Os dois scopes exclusivos terminaram com código zero e `inactive/dead`; as cópias dos pesos permaneceram nos inodes autenticados. Zero servidores ou forwards novos. A energia total da máquina não tem medição nesta unidade.

Esta fixture cronometra os 797 jobs que o banco causal das últimas vítimas ainda vai buscar ao disco nas 46 avaliações do T2 ON R02. O GGUF e o pack integral entregam as mesmas 2 391 matrizes MXFP4 em cada travessia. O predicado de admissão, a ordem, os hashes e os recursos foram congelados em `a37e2c6a`, o programa e a contraprova em `0224d2667fd4ff922ffc3dbb5075e36f60ed95fb` (árvore `3356fe05cf981c9bfd88453f094089f98ac4f57d`). [Protocolo](protocol.md) · [Plano e ligação das matrizes](../protocol.md)

**População.** Em 632 das 1 656 callbacks há pelo menos um pedido ao disco. As outras 1 024 conservam lugar e posição com zero READ. O plano fixa 541 jobs em camadas de experts CPU e 256 em camadas de experts CUDA; as 399 admissões de banco ficam disponíveis ao revisor para contabilizar o seu SET. Cada braço lê 10 535 702 400 B de payload. O GGUF pede 10 545 446 912 B em 2 391 preads; o pack pede 10 537 844 736 B em 797 preads. O índice do C290 estabelece posições e hashes gate/down/up; os dois FDs O_DIRECT são confrontados com dev, inode, tamanho, mtime e ctime. O plano privado tem SHA-256 `aed09397a16ed706365d73e0d2535427528476b41d66e3d5e43ad90da345d79a`; o recibo de preparação é `faa756041cab0f35b12ed06a91058e54b389582839820ea265dad69c52b19993`. A preparação do pack no NVMe custou anteriormente uma escrita e uma releitura locais do ficheiro selado de 61 096 329 216 B, além da leitura da origem. [Colocação integral e recibos](../../../../../../../t1_full_pack_service/README.md)

**Relógio.** Quatro threads persistentes esperam a publicação de cada grupo. Os jobs elegíveis seguem a FIFO das reservas, cada geração tem buffer distinto e a barreira termina quando todos os workers regressam. Os intervalos de pread pertencem ao worker que os executou. A verificação de todas as três matrizes ocorre fora da janela de serviço, antes de reciclar o buffer e antes do grupo seguinte. A escrita de logs, o monitor e a programação do grupo seguinte também espaçam os dispatches. Os blocos físicos abrangem tudo o que o dispositivo serviu na travessia. O_DIRECT evita a cache de páginas neste FD. O estado interno do controlador e a contenção no SSD podem mudar entre travessias. O destino final dos experts, a captura do banco e os tempos dos SETs requerem outra medição.

**Admissão.** O portátil usou Ryzen AI 9 HX 370, NVMe interno sobre Btrfs, AC/performance e provider NVML compatível com driver 620.70.06. A RTX 4060 Laptop de 8 188 MiB serviu para telemetria. A C55 em tmpfs recusou 11 512 881 152 B livres para raws (limiar 11 GiB). A segunda C55 preservou o erro de inventário da tentativa de usar o volume USB para os raws. A terceira usou `/var/tmp` no NVMe, com 96 203 952 128 B livres e 61 amostras. Recibos dos dois primeiros estados `0f6e2c0afc2a5077d988d777c975b224458b8771208799a6e6718825a9370a2c` e `402c8061afc0b259daa3c6d018ab56554ce942744cdcd547aeddc2b8fd44f0e3`. A janela admitida tem SHA-256 `7a777b4d4036173fb90c5e742468def9d1d37d2f7df7e6dcf7c97ea656e74838`. O manifesto privado da parte 65 contém o plano e os dois primeiros recibos, SHA-256 `1713b1e73b8e59c34b1f12fc268a9d6caafba09d5c82707476ec9a0febd0069b`.

Para reproduzir com as cópias já autenticadas, usar uma checkout limpa do commit indicado e uma C55 fresca do portátil. `PLAN` é o plan.json privado, `C55`, `R_PLACEMENT` e `P_PLACEMENT` são os três recibos das autoridades. Cada processo recolhe a sua C118. `UNIT` e `OUT` são exclusivos; repetir a invocação com processo 2 depois do PASS do primeiro, fornecendo `--prior-receipt` e o seu `--prior-sha256`.

```sh
u=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/replay/decode_clock/transport/service
python3 -IB "$u/test_measure.py"
systemd-run --user --scope --quiet --collect --unit="$UNIT" \
  -p MemoryHigh=384M -p MemoryMax=384M -p MemorySwapMax=0 -- \
  env LD_LIBRARY_PATH="$MONITOR_LIB" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  /usr/bin/python3 -IB "$u/measure.py" --commit 0224d2667fd4ff922ffc3dbb5075e36f60ed95fb \
  --unit "$UNIT" --plan "$PLAN" --plan-sha256 aed09397a16ed706365d73e0d2535427528476b41d66e3d5e43ad90da345d79a \
  --placement "$R_PLACEMENT" --pack-placement "$P_PLACEMENT" \
  --c55 "$C55" --c55-sha256 "$C55_SHA" --process 1 --new-output-dir "$OUT"
```
