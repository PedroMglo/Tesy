# Blocos de três posições numa sequência viva

**GO para testar rejeições com prefill vivo. NO_GO para substituir a sequência viva pelo seu restauro neste contrato bitwise.** No 120B original, o cliente sem observador produziu os mesmos quatro vetores completos e o mesmo KV com execução serial e em bloco. Um terceiro processo repetiu todo o prefill, manteve exatamente a mesma residência dos experts, apagou o KV e importou a sua própria serialização. Os bytes de entrada eram os mesmos. As quatro distribuições divergiram depois dessa operação. [Protocolo anterior à medição](protocol.md) · [Resultados por braço](evidence/three-processes.json)

| Braço | Prefill, KV e pool de entrada | Logits F32 diferentes do serial nas quatro posições | Palavras F16 diferentes no KV pós-bloco | Tempo do processo / pico RTX |
| --- | --- | --- | ---: | --- |
| AR, histórico vivo | Referência | 0 / 0 / 0 / 0 | 0 | 26,543 s / 6 866 MiB |
| B3, histórico vivo | Iguais a AR | 0 / 0 / 0 / 0 | 0 | 26,344 s / 6 862 MiB |
| B3, restauro do próprio histórico | Mesmos bytes e experts, mínimo público 61 | 201 086 / 201 084 / 201 087 / 201 085 | 24 797 | 26,567 s / 6 862 MiB |

Cada vetor tem 201 088 F32 finitos. Os três braços escolheram os mesmos quatro IDs greedy. AR e B3 vivos também coincidiram com as cinco saídas da parte 169, incluindo o prefill. O primeiro vetor do restauro quente igualou bit a bit o restauro frio da parte 171. No restauro quente, as diferenças no KV limitaram-se às três posições novas e às camadas 27–35, num total de 5 898 240 F16 comparados. O primeiro desacordo materializado encontra-se em K da camada 27. O emparelhamento identifica o efeito da operação de restauro nesta execução. O mecanismo aritmético interno que propagou a diferença continua por isolar. [Primeiro restauro](../README.md) · [Referência instrumentada](../../b3_numeric/first_boundary/router_row/integrated/input_l25/ffn_cuda/target/README.md)

MEDIDO no portátil, biblioteca `851fe6a3`, cliente `3bd6ba7f` como revisão de build e medição `070f0b47`. Cada braço recebeu 189 IDs de prefill numa chamada ub32 e quatro IDs fornecidos. Três arranques com C118, zero pedidos HTTP e zero swap. O processo inclui carga, prefill e gravação dos estados. A potência amostrada da GPU integrou aproximadamente 315,0 / 309,9 / 312,6 J nos intervalos cobertos. A energia total do portátil é DESCONHECIDA. O próximo teste alimenta a âncora greedy real e verifica as propostas rejeitadas e os dois tokens seguintes. M3 PARTIAL, M4 NOT_MET.

O arquivo selado contém 99 ficheiros e 125 237 650 bytes. A reprodução independente nos originais e no arquivo gerou o SHA-256 `c2f12299e47ad025401cd20f82b34f0999222971f28e2e82f3cce79d83087a78`. A partir da raiz do repositório, indicar as famílias anteriores e um destino novo. [Manifesto privado](../../../private_archive/part-172.json) · [Revisor sem GPU](review.py)

```sh
python3 research/qualification-retake/history_lookup/target_rollback/live_prefix/review.py \
  --family "$FAMILY_172" --family-sha256 aa9c70514463e4477dd298ccb5284a0d4c6aaf1e951d2d9982d57d95910578a9 \
  --build "$BUILD_172" --window "$C55_172" --target "$FAMILY_169" --serial "$FAMILY_165" \
  --reference "$C270_161" --cold-import "$FAMILY_171" --new-output-dir "$NEW_RESULT"
```
