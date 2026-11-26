# O target rejeita o sufixo e conserva a conversa

**GO para integrar e medir a proposta causal.** Com o GPT-OSS-120B original, um prefill vivo de 189 posições e o observador desligado, o target confirmou os mesmos IDs e distribuições que a referência serial nos três casos provocados. A âncora greedy foi 410. Os cinco IDs seguintes da referência foram 190125, 50005, 5671, 31935 e 1127. As entradas do prefill e a residência inicial coincidiram com os controlos físicos da parte 172. [Pré-registo](protocol.md) · [Resultado e hashes](evidence/greedy.json) · [Controlos da sequência viva](../live_prefix/README.md)

| Aceites em duas propostas | Proposta fornecida | ID confirmado na decisão | Dois IDs seguintes | Linhas F32 consultadas na decisão | Experts exclusivos do candidato após a decisão, CPU / CUDA |
| ---: | --- | ---: | --- | ---: | ---: |
| 0 | 54349, 50005 | 190125 | 50005, 5671 | 1 | 71 / 33 |
| 1 | 190125, 6400 | 50005 | 5671, 31935 | 2 | 38 / 12 |
| 2 | 190125, 50005 | 5671 | 31935, 1127 | 3 | 0 / 0 |

As seis linhas consultadas e as seis linhas seguintes igualaram AR bit a bit, cada uma com 201 088 F32 finitos. O KV serializado coincidiu nas nove comparações de corte e continuação. O parser reabriu os dois bancos e todos os cabeçalhos. As rejeições chamaram `llama_memory_seq_rm` uma vez e conservaram respetivamente uma e duas posições do bloco. A aceitação dupla manteve as três posições. Na rejeição imediata, a referência ainda tinha 71 experts CPU e 27 CUDA ausentes do candidato. Depois de dois tokens, o candidato ainda tinha 42 CPU e 20 CUDA exclusivos. Mesmo com aceitação dupla ficaram seis slots CPU com atribuição física distinta, embora o conjunto residente coincidisse. Esses efeitos entram no preço da tentativa seguinte.

MEDIDO em quatro processos no portátil, commit `568e9c35`, biblioteca `851fe6a3`, quatro workers, 40 slots, ctx8192 e NVMe. C118 antecedeu cada processo. O máximo foi 6 866 MiB na RTX, 15 761 231 872 B no cgroup e zero swap. Os processos duraram 26,048–27,227 s incluindo carga, prefill e gravações. A estimativa de energia da GPU foi 299,4–320,9 J nos intervalos amostrados. Energia do host DESCONHECIDA. Foram zero pedidos HTTP. A taxa de aceitação foi imposta pela fixture. As cinco decisões desta trajetória que um bigrama causal veria são todas AR. A trajetória nominal histórica forneceu onze propostas efetivas. A qualificação de produto continua M3 PARTIAL e M4 NOT_MET. [Proponente C269 na conversa nominal](../../native_ids/b3_fixture/README.md) · [Orçamento do pedido](../../packed_step_budget/frontier.md)

O arquivo tem 140 ficheiros e 238 811 570 bytes. O revisor reproduziu o SHA-256 `3ac3e1468751c00c807c6f2799507c1e9f21a14d69b8208b83a174f41e423708` nos originais e na cópia selada. Cada destino de reprodução deve ser novo. [Manifesto](../../../private_archive/part-173.json)

```sh
python3 research/qualification-retake/history_lookup/target_rollback/live_rollback/review.py \
  --family "$FAMILY_173" --family-sha256 9f384fe141eac5b8aa28128d778565870884f4f18c5105b4f7761c62548a3d86 \
  --build "$BUILD_173" --window "$C55_173" --target "$FAMILY_169" --serial "$FAMILY_165" \
  --reference "$C270_161" --live-control "$FAMILY_172" --new-output-dir "$NEW_RESULT"
```
