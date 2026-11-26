# A leitura seletiva preservou os logits do pequeno grafo CUDA

**GO para testar os dois cortes C110 no 120B.** O cliente residente independente, o banco com origem GGUF mapeada e o banco com leitura explícita reproduziram as mesmas 1 024 palavras F32 após o prefill e as mesmas 32 após o primeiro decode. Os 66 quartetos ordenados coincidiram. Reabrir os dois controlos históricos no mesmo driver produziu os mesmos resultados. O pedido natural mais rápido do 120B continua em 18,313 s até ao primeiro conteúdo final e 5,361 tok/s. [Resultado por braço](result.json) · [Medição da conversa](../../../../../packed_nvme_manifest/server_profile/conversation/ordens.md)

| Grafo, 32+1 posições | Origem física das matrizes | SET / cópias para o banco | Pico de VRAM observado | Palavras F32 diferentes do residente |
|---|---|---:|---:|---:|
| RESIDENT | Pesos residentes na RTX | 0 durante os forwards | 134 MiB | 0 |
| DIRECT | Mapeamento do GGUF | 24 / 24 | 130 MiB | 0 |
| PREAD_RANDOM | Scratch anónimo, preenchido por pread | 24 / 24 | 130 MiB | 0 |

Em cada banco, as quatro leituras assíncronas de IDs e as quatro barreiras reais da cache devolveram os ranks do router nas duas camadas e duas fases. Nas fronteiras havia 0, 9, 12 e 3 SET desde a barreira anterior. A última camada fez só hits no decode. O cleanup encontrou zero fontes pendentes. A fixture diferida anterior cobre o caso em que ainda há trabalho no destrutor. Os 10 fills do prefill transferiram 1 044 480 B das três matrizes. O decode fez 7 hits e 1 fill de 104 448 B. O máximo vivo com padding foi 552 960 B de uma reserva de 1 MiB em ambos os braços. O auditor juntou cada origem física à sua fatia no GGUF, ao seu destino real na RTX e à submissão do consumidor. [Verificador de endereços e coberturas](grade.py) · [Teste de consumo diferido e falhas](../README.md)

MEDIDO no portátil, RTX 4060 Laptop, driver 620.73.04, ik `7a5d9000`. O pré-registo foi `b2f98248` e o commit físico `5db4ec21`. Três processos, seis forwards do GGUF determinístico de 3 390 592 B, 24 consumidores por braço. O scope atingiu 536 559 616 B de RAM, swap zero e zero eventos de OOM. Energia integrada DESCONHECIDA. A comparação integral de bytes na entrega e o callback fazem parte da prova de exatidão. A medição do custo no pedido natural requer uma unidade própria. Este resultado preserva M3 PARTIAL e M4 NOT_MET. [Protocolo e critérios](protocol.md) · [Manifesto do lote 150](../../../../../private_archive/part-150.json)

Para reproduzir a decisão sem GPU a partir do arquivo, indicar as pastas dos lotes 150 e 143 e o GGUF minúsculo original usado nesses processos. O revisor valida o inventário e reabre os endereços reais, os logits e as rotas. Original e arquivo deram o mesmo JSON, SHA-256 `bcb4f2acca1c72a96f3d49f789921d05140e440202e965956344dc7d3466d907`.

```sh
python3 -IB review.py --family "$FAMILIA_150" --historical "$REFERENCIA_143" \
  --tiny "$GGUF_PEQUENO" --new-output-dir "$NOVA_SAIDA" \
  --family-sha256 d0973e97224a3136c168184c1715fe2e4e32acf664036a8a71728699fae6438d
```
