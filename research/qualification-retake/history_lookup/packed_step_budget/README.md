# O pack junto da proposta de dois tokens

**Mesmo com B3 gratuito, os dois braços de pack projetam 14,446 e 14,280 s até ao primeiro conteúdo final.** A medição original do cliente foi de 18,515 e 18,313 s. Em ambos, a primeira peça final é a amostra 45 de 47. Até esse ponto, 23 avaliações AR não tinham proposta. Das outras 21 avaliações, dez estavam nas posições em que B3 verificaria uma proposta e onze deixariam de executar AR. A proposta restante e a última avaliação AR evitável caem depois do primeiro delta. [Pré-registo](protocol.md) · [Recibo R/O/P](rop.json) · [Recibo P/O/R](por.json)

| T2 com pack | P em R/O/P | P em P/O/R |
|---|---:|---:|
| Prefill do servidor, 153 tokens | 9,821734 s | 9,783740 s |
| Decode do servidor, 47 saídas e 46 avaliações AR | 8,930493 s | 8,767606 s |
| Primeiro conteúdo final medido pelo cliente | 18,514554 s | 18,312926 s |
| Tempo das 23 AR ordinárias, pela marca de amostragem | 4,614660 s | 4,485825 s |
| Crédito favorável pelas outras 21 posições até à peça 45 | 4,068384 s | 4,032766 s |
| Cauda posterior excluída desse crédito | 0,247451 s | 0,249018 s |
| Primeiro final com verificações e coordenação gratuitas | **14,446170 s** | **14,280160 s** |
| Redução adicional mínima de prefill ou trabalho exterior exposto para 10 s | **4,446170 s** | **4,280160 s** |
| Máximo médio por verificação, com coordenação, para 6 tok/s no decode completo | **292,607 ms** | **304,319 ms** |

A meta de 10 s já fica fora de alcance com verificações gratuitas nas dez propostas que antecedem o primeiro final. Se a redução viesse inteiramente do prefill, este teria de cair para **5,376 e 5,504 s** ou menos. Para o alvo isolado de débito, distribuem-se 47/6 s pelas 23 AR restantes e onze verificações. O segundo marcador de controlo, a entrada do token no lote seguinte, projeta 14,446164 e 14,280165 s até ao primeiro final e admite 292,605 e 304,317 ms por verificação para o débito. [Regra e controlo nativo das propostas](../native_ids/b3_fixture/README.md) · [Antecedente de custo posicional](../native_ids/step_cost/README.md)

O crivo confronta o SHA do braço, o FD do pack, o processo encerrado, os dois vetores de IDs e as projeções dos dois turnos. Liga as duas peças finais a deltas SSE distintos, pela ordem e bytes, após o único marcador Harmony de final. A duração até ao primeiro final pertence ao cliente; os intervalos por posição são marcas textuais de DEBUG do servidor. A conta conserva o custo das AR ordinárias e a entrega exterior e assume que remover trabalho antes da peça 45 antecipa a entrega pelo mesmo intervalo. A resolução do logger e a fila de transporte deixam por identificar um piso incondicional no relógio do cliente. O custo real das verificações precisa de outra prova. No controlo numérico C127, B3 e AR deram argmax igual nas quatro linhas, mas divergiram nos quatro vetores de logits e no KV posterior ao bloco. [Prova de exatidão e limites](../b3_numeric/README.md) · [Contas anteriores para prefill e decode conjuntos](../joint_budget/README.md)

O protocolo foi congelado em `37b86b25`. Três testes sintéticos cobrem fronteira textual ambígua, exclusão da cauda, contagens e monotonia. Cada cálculo usou 0,06 s, com 23 608 e 23 980 KiB de RSS. A réplica foi admitida após o fecho da família P/O/R, SHA-256 de family.json 9428a171c354c6cd2d3f12ecb338249ac33be9ced2633ab8c4fdddbdd2b3e284. [Verificador](screen.py) · [Contraprovas](test_screen.py)

```sh
study=research/qualification-retake/history_lookup/packed_step_budget
python3 -IB "$study/test_screen.py"
timeout 120 prlimit --as=268435456 -- python3 -IB "$study/screen.py" \
  --arm "$FAMILY/P" --arm-sha256 "$ARM_JSON_SHA256" --output "$NEW/receipt.json"
```
