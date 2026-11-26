# Vocabulário oficial nos dois turnos Aster

**MEDIDO · PASS_OFFICIAL_VOCAB_ONLY.** Com a data congelada, C269 e o stock e95426f reproduziram todos os IDs de entrada de C133. O stock com a Jinja original produziu sequências do mesmo comprimento com dois IDs diferentes em cada turno. Esta diferença seria invisível numa conferência apenas da contagem de tokens. [Protocolo](protocol.md) · [Recibo da execução](attempt-03/receipt.json)

| Turno | IDs de C133 | Posições divergentes em C269 | Stock, Jinja original | Stock, Jinja com data vinculada |
|---|---:|---:|---:|---:|
| Primeiro pedido | 121 | 0 | 2 | 0 |
| Segundo com final histórico | 435 | 0 | 2 | 0 |

A chamada de leitura pediu 13 022 240 bytes à cópia NVMe do target com o SHA-256 previamente verificado e o tuplo de ficheiro da C55 r3. Esse intervalo termina no início dos tensores. O parser GGUF encontrou 687 descritores. A cópia privada para o tokenizador conservou as 36 chaves de metadados, incluiu zero tensores e ocupou 12 980 384 bytes. C269 e stock confirmaram um vocabulário de 201 088 tokens e a mesma Jinja embebida `a4c9919cbbd4acdd51ccffe22da049264b1b73e59055fa58811a99efbd7c8146`. A Jinja separada do braço stock com data vinculada tem SHA `0ccef2b31697ba30f891ed18cfc1203b8603f26fc4233faa98839c674819b9eb`. O modelo original ficou intacto. [Prova dos bytes de render](../aster_template/README.md)

A checkout de medição estava limpa e destacada em `7f11bf3407f06fef385880697dee3f755c0eb213`. Os cinco processos monitorizados consumiram 1,557 s de parede somados e atingiram 296 832 KiB de RSS amostrada. A pasta privada ocupou 26 110 220 bytes, incluindo os binários e logs. A operação não executou forwards nem usou GPU. O tráfego físico do NVMe e a energia ficaram por medir. Nas duas primeiras tentativas, a checkout esparsa omitia `workloads/c133_diverse_session.json`. Na segunda, o comando de Git usado para acrescentar o caminho foi rejeitado. O guardião de entrada encerrou ambas antes da leitura do artefacto. A terceira usou o mesmo commit e limites, com o caminho incluído. [Primeira tentativa](attempt-01/receipt.json) · [Segunda tentativa](attempt-02/receipt.json)

O comprimento do prefixo comum entre os dois prompts é 121. A pilha de KV inclui ainda a geração anterior. Atribuir o segundo turno a C133 requer observar no próprio serviço 122 tokens reutilizados e 313 novos, bem como a sequência exata de 435 IDs. Para o produto é indispensável a resposta natural ao primeiro turno, a conclusão válida e a mensagem final do segundo. Os resultados de cache, geração e produto permanecem `NOT_RUN` nesta unidade. [Comparador dos dois modos de histórico](../two_turn.md)

### Reprodução no portátil

O primeiro comando do protocolo de render fornece a pasta privada com os clientes C269/stock e a Jinja com data vinculada. Indicar as mesmas checkouts e a pasta de resultados históricos de C133, o recibo completo da colocação NVMe e o da C55 r3. As saídas são exclusivas por tentativa.

```sh
python3 -B research/qualification-retake/aster_vocab/verify.py \
  --c269-source "$C269_SRC" --c269-bin "$C269_SRC/build-c269-cuda/bin" \
  --stock-source "$STOCK_SRC" --stock-bin "$STOCK_SRC/../build/bin" \
  --historical-results "$C133_RESULTS" --render-workspace "$RENDER_PRIVATE" \
  --placement "$NVME_PLACEMENT_RECEIPT" --window "$C55_R3_RECEIPT" \
  --private-workspace "$NEW_PRIVATE" --new-output-dir "$NEW_REPORT"
```
