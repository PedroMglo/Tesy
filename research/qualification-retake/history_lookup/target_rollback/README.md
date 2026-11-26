# Restauro do histórico e primeira decisão de rejeição

**INCONCLUSIVE na calibração. Os três casos de rejeição ficaram NOT_RUN.** O cliente sem observador importou e voltou a escrever os mesmos 11 690 596 bytes do KV de 189 posições. No primeiro vetor de calibração, 201 086 dos 201 088 logits F32 diferiram do braço CUDA da parte 169. Ambos escolheram o ID 4572. O erro absoluto máximo foi 0,115210 e a raiz do erro quadrático médio 0,020959. A igualdade do argmax cobre esta posição. A comparação exigia igualdade bitwise do vetor completo. [Calibração reaberta](evidence/import-171.json) · [Referência da parte 169](../b3_numeric/first_boundary/router_row/integrated/input_l25/ffn_cuda/target/README.md)

| Parte | Condição no mesmo 120B e biblioteca | Primeiro resultado observado | Processo / pico RTX |
| --- | --- | --- | --- |
| 170 | Importar a referência serial e exigir mínimo público zero | O backend leu 189 e 128 células. O cliente parou antes do primeiro decode. Os valores públicos ficaram sem registo. | 2,575 s / 6 694 MiB |
| 171 | Observar o intervalo público e verificar os dois bancos da sequência | Mínimo 61, máximo 188. O KV de entrada coincidiu byte a byte. Um decode com três IDs fornecidos completou. O primeiro vetor divergiu e encerrou a família. | 4,644 s / 6 810 MiB |

No C269, `llama_kv_cache_iswa::seq_pos_min/max` consulta o banco deslizante. A serialização de uma sequência filtra as posições mascaradas. O parser confirmou as posições 0–188 no banco global e 61–188 no deslizante, 11 412 linhas K/V e 18 camadas por banco. O protocolo corrigido exigiu essas posições, as distribuições e o KV de referência. Cada identidade teve um arranque, 61 amostras de inventário C118, zero swap e zero pedidos HTTP. Os tempos incluem arranque do processo. Os recibos retêm os máximos térmicos e de memória. [Primeira falha](evidence/import-170.json) · [Primeiro protocolo](protocol.md) · [Critérios do restauro SWA](swa-restore-protocol.md)

O contraste com a parte 169 alterou o observador, a construção física do KV e a residência inicial dos experts. A referência da parte 169 construiu o prefill no processo e inspecionou o grafo. O cliente da parte 171 importou a sequência num contexto novo. Essa comparação deixa a causa numérica em aberto. As propostas controladas com zero, uma ou duas aceitações, a sua truncagem e a velocidade de uma conversa continuam por qualificar. O próximo contraste usa uma referência serial contemporânea e um bloco de três, ambos sem observador e com prefill nativo.

### Reprodução sem GPU

Cada parte usa o build, o C55 e a família da identidade respetiva. `TARGET_169` designa a raiz da família física da parte 169. O revisor reabre a lista completa de hashes, os dois bancos de entrada, o C118 e os logits disponíveis. Os resultados do original e da cópia privada selada coincidiram para as duas partes. [Manifesto 170](../../private_archive/part-170.json) · [Manifesto 171](../../private_archive/part-171.json)

```sh
python3 research/qualification-retake/history_lookup/target_rollback/import_failure.py \
  --family "$FAMILY" --build "$BUILD" --window "$WINDOW" --target "$TARGET_169" \
  --new-output-dir "$NEW_RESULT"
```
