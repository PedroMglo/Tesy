# Capacidade/loader — inventário instalado e cenários maiores

Classificação: **MEDIDO** apenas para inventário/recursos do gpt-oss-20b instalado; **ESTIMADO** para reservas e floors de transporte; candidatos maiores **DESCONHECIDO** quanto à admissão exacta. Ferramenta reproduzível `src/tesy/vertical_capacity.py` (schema `tesy.vertical_capacity_report.v1`), root local `results/vertical-capacity-20260924T220300Z/report.json`, SHA-256 `4331fe996bdc9c6e0b4cf47fc209f14a5747efbf428820b2816d86c28b45c50c`.

O `report.json` bruto está agora incluído no [bundle público de evidência](https://github.com/PedroMglo/Tesy/releases/download/evidence/full-model-vertical-20260924-v1/tesy-vertical-raw-evidence-20260924.tar.gz), com path interno `results/vertical-capacity-20260924T220300Z/report.json`.

Host físico: RAM 32 698 769 408 bytes, VRAM 8 585 740 288 bytes. Reservas explícitas para classificação: 6 GiB host operacional + 1 GiB staging/I/O + 1 GiB VRAM. Estas reservas são política de admissão, não peak observado. O installed GGUF tem 12 109 564 352 encoded bytes, SHA-256 congelado `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`. Na root stock C1 houve peak process RSS 12 764 119 040 bytes e GPU usada 333 447 168 bytes; a diferença RSS menos artifact (654 554 688) **não** isola repacking. O buffer nativo Tesy para quatro residentes de uma layer foi observado em 53 015 424 bytes; não multiplicar sem contabilizar graphs, temporários e aliasing. No grupo stock final o peak GPU usado chegou a 6 020 923 392 bytes em `n_gpu_layers=12`, mas isto é colocação stock, não residência Tesy.

| Artefacto | Base de bytes | Classe | Em falta para admissão |
|---|---|---|---|
| gpt-oss-20b GGUF instalado | 12 109 564 352 exactos | encoded weights cabem no orçamento RAM declarado; runtime stock observado | loader >RAM não inferido |
| Qwen3-30B-A3B-Instruct Q4_K_M | fonte reportou 18,557 GB, sem artifact exacto | artifact bytes desconhecidos | revision, bytes, SHA-256, inventory/alocações |
| gpt-oss-120b MXFP4 | checkpoint reportado 60,8 GiB, superior à RAM; GGUF exacto desconhecido | checkpoint reportado >RAM, não execução admitida | revision, GGUF bytes/SHA, loader working set |

O loader stock e o candidato com tensors emprestados precisam do namespace completo dos pesos antes do decode. O modelo é carregado por mmap, mas **mmap span não é DRAM residente**; não foi demonstrado se há materialização física de todos os pesos nem se um modelo >RAM se manteria estável sem swap. Para candidatos próximos do orçamento, faltam encoded bytes exactos, materialização/repacking, KV por contexto, duplicações host/GPU, workspace, page cache, I/O buffers e margem operacional. Não há autorização para descarregar/executar Qwen ou 120B nesta unidade.

Floor puramente parametrizado `bytes necessários / bandwidth sustentada`: 1 GiB exige ≥1,074 / 0,358 / 0,215 s a 1/3/5 GB/s; 4 GiB ≥4,295 / 1,432 / 0,859 s; 16 GiB ≥17,180 / 5,727 / 3,436 s. Não são physical I/O observado, nem tok/s previsto. Cache/reuse e bandwidth físico válido do workload maior estão em falta. O manifest de modelos marca revision/bytes/SHA em falta; a ferramenta tem testes model-free para as classes `ENCODED_WEIGHTS_RAM_ADMISSIBLE_ONLY`, `WORKING_SET_NEAR_HOST_BUDGET` e `WEIGHTS_EXCEED_RAM`.
