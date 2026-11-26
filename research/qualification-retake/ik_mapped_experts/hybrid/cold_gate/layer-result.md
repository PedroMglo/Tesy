# A leitura seletiva entregou os três pesos da camada mais cedo

**GO para integrar o percurso de leitura no backend experimental.** Na camada 0 do prefill C110, a leitura explícita dos intervalos serviu os mesmos 647 740 800 B de gate, up e down **225,279 e 168,124 ms mais cedo** do que o mmap direto, nas duas ordens. Os bytes de leitura cobrados ao cgroup diminuíram de 1 553 981 440 para 648 155 136 em cada par. A margem para custos adicionais nesta fixture é inferior a 168,124 ms para preservar ambos os sinais positivos. [Critério prospetivo](layer-protocol.md) · [Resultado por braço em ns e bytes](layer-result.json)

| Ordem e braço | Serviço até à barreira (ms) | Preparar origem (ms) | Submeter H2D (ms) | Drain (ms) | PID e cgroup (MB) | Namespace na barreira → corte tardio (MB) |
|---|---:|---:|---:|---:|---:|---:|
| Direto primeiro · DIRECT | 617,067 | 0,170 | 616,137 | 0,061 | 1 553,981 | 1 547,723 → 1 554,010 |
| Direto primeiro · PREAD_RANDOM | 391,787 | 346,145 | 45,355 | 0,081 | 648,155 | 648,155 → 648,155 |
| Random primeiro · PREAD_RANDOM | 401,219 | 355,052 | 45,827 | 0,090 | 648,155 | 648,155 → 648,155 |
| Random primeiro · DIRECT | 569,344 | 0,138 | 568,627 | 0,046 | 1 553,981 | 1 548,100 → 1 553,981 |

Cada braço começou com as 413 103 páginas das três matrizes frias. Os 99 destinos CUDA foram verificados integralmente contra o pread independente, incluindo as seis guardas e a ordem dos SET reais. O candidato conservou 52 747 páginas por matriz depois da barreira. O direto conservou entre 126 398 e 126 593. A verificação posterior consumiu 312–315 ms por braço. O scratch de 648 155 136 B esteve reservado e foi tocado nos dois caminhos. Estes tempos cobrem a entrega completa de três matrizes de uma camada. O tempo de cálculo, a cache entre camadas, o prefill de uma conversa e o decode continuam por medir com este mecanismo integrado.

**Produto.** A melhor observação do cliente com o pack do Tesy continua em **18,313 s até ao primeiro conteúdo final, 18,565 s até à resposta válida e 5,361 tok/s**. Foram recuperados 2 044 tokens de histórico e acrescentados 153. O objetivo nominal é ≤10 s e ≥6 tok/s na mesma receita. O pack usa outro percurso de I/O. Quantificar o ganho combinado exige medir a combinação com R0 contemporâneo e uma ablação no mesmo backend. M3 PARTIAL e M4 NOT_MET. [Duas ordens de pedidos naturais e controlos](../../../packed_nvme_manifest/server_profile/conversation/ordens.md)

## Prova física e reprodução

A etapa de integração começou por um leitor C++ que mantém a origem válida até à barreira de cada backend. O teste de um consumidor diferido passou nos dois modos, incluindo falha após submissão e cleanup. O próximo discriminante é a paridade no grafo CUDA BANK9 com a origem de cópia alterada. [Implementação e resultado sem modelo](backend_input/README.md)

No portátil, o commit físico de R02 foi `db782057b1ed11f772fe914de07e9d193066619f`, em árvore limpa. O GGUF foi o original do NVMe interno e o driver da RTX 4060 foi o 620.73.04. Os dois C118 contaram 61 amostras em 60,160 e 60,150 s. A vida dos filhos incluindo cleanup foi 3,106 e 3,494 s. Pico no scope 2 315 829 248 B, VRAM 720 MiB e swap zero. Nos monitores dos filhos a CPU chegou a 58,25 °C, a GPU a 44,67 °C e o NVMe a 36,85 °C. O scope encerrou e a RTX regressou a 2 MiB. Energia integrada DESCONHECIDA. R01 fica preservado, com um arranque e zero SET cronometrados. Na família R02 houve dois arranques, quatro provas de bytes, zero forwards do modelo e zero pedidos HTTP. Os relatórios calculados sobre os originais e o arquivo coincidiram. [R01, diagnóstico e condição de reabertura](layer-diagnostic.md) · [Lote privado 148, 22 ficheiros e 256 666 B](../../../private_archive/part-148.json)

```sh
d=research/qualification-retake/ik_mapped_experts/hybrid/cold_gate
family="$ARCHIVE/part-148/tesy-ik-cold-gate-layer-20261126-r02"
ref="$ARCHIVE/part-147/tesy-ik-cold-layer-reference-20261126-r01/receipt.json"
python3 -IB "$d/grade.py" --family "$family" --reference "$ref" \
  --family-sha256 07270ab2dc885128493e386a65a689f35f9dc915fa216ace2628c66c45956561 \
  --new-output-dir "$NEW"
python3 -IB research/qualification-retake/private_archive/verify.py \
  "$ARCHIVE" research/qualification-retake/private_archive/part-148.json
```
