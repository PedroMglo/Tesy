# A CPU pode omitir o interior de uma wave inteira?

**GO_FIXTURE para a estrutura do grafo.** O backend C269 aceitou o mesmo grupo contíguo de seis operações nas oito waves da tile CPU0. Cada grupo contém as projeções gate e up, os respetivos ADD_ID, o SwiGLU OAI e a projeção down. Só o valor do down sai da região. O bias de down, a máscara, a soma ordenada e o remap continuam visíveis. Esta observação admitiu escrever uma fixture numérica para o caso em que todos os IDs físicos são −1. [Recibo por wave](physical-r01/receipt.json) · [Protocolo numérico](numerical/protocol.md)

| Wave | Intervalo de índices na vista CPU | Remap | Bias de down | Máscara |
|---:|---:|---:|---:|---:|
| 0 | 2–7 | 1 | 8 | 9 |
| 1 | 14–19 | 13 | 20 | 21 |
| 2 | 27–32 | 26 | 33 | 34 |
| 3 | 40–45 | 39 | 46 | 47 |
| 4 | 53–58 | 52 | 59 | 60 |
| 5 | 66–71 | 65 | 72 | 73 |
| 6 | 79–84 | 78 | 85 | 86 |
| 7 | 92–97 | 91 | 98 | 99 |

**MEDIDO no portátil.** A primeira observação recebe o grafo lógico construído pela fixture. A segunda recebe a vista entregue pelo scheduler à CPU no ponto de entrada de ggml_graph_compute. O observador termina antes de executar os kernels. Ambas reproduzem o fingerprint e569253a2f984a84, 110 nós e 24 MMID da referência; o scheduler produziu um split. O predicado ggml_can_fuse_subgraph_ext, os contadores de uso e as arestas confirmam que nenhum intermédio omitido tem consumidores externos. Os cálculos de bias por expert lógico e da acumulação por wave precisam de manter o sinal de zero. [Pré-registo](protocol.md) · [Extrator e chamada do predicado nativo](seam.cpp)

O ensaio, incluindo compilação, levou 5,440 s na checkout limpa 9cf3a726fd6445bc37aa49325646825f01f2acc8, árvore 595b35879964d0217a126425a5f27b73cb4de20d. O pico do cgroup de 4 GiB foi 373 780 480 B. A entrega ao backend reservou 528 768 000 B para caches de pesos, 4 423 680 B de bias e 6 268 416 B no scheduler. Nenhum peso foi lido, nenhum worker arrancou e nenhum operador do grafo foi executado. As reservas virtuais e o pico residente têm denominadores distintos. As durações da conversa e da tile pertencem às campanhas que realmente executaram esses grafos. [Última comparação temporal da tile](../parked_mmid/README.md)

O comando reproduz a decisão a partir dos dois grafos arquivados. Cada execução exige um novo destino.

```sh
python3 -IB research/qualification-retake/parked_fusion/compact.py \
    --raw-root "$TESY_GRAPH_R01" \
    --receipt-sha256 a6c64aa78e3c11bb385aaa437d314f05f18b27ff1bf78dc6f9bcc37c50faef04 \
    --new-output-dir "$NOVO_COMPACTO"
```
