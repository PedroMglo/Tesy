# Margem conjunta até ao primeiro conteúdo final

**INCONCLUSIVE para o produto.** As 34 chamadas identificadas na trajetória nova dão margem para estudar o decode. A 4,5 GB/s, se pelo menos o piso de 12,945 GB do contador do processo tiver de ser servido dentro do prefill, o limite conjunto de **10 s até ao primeiro final e pelo menos 6 tok/s** exige que cada verificação B3 custe **no máximo 1,040 chamadas AR** em média, concedendo zero custo adicional exposto. O critério isolado dos 6 tok/s admitia 1,232. [Crivo de chamadas](../native_ids/README.md) · [Volume e relógios por fase](../../nvme_conversation/phase_reads/README.md)

| Bytes assumidos obrigatórios na fase | Só leitura a 4,5 GB/s | Decode máximo | Taxa de decode exigida | Custo B3 máximo em AR | Folga conjunta com B3 a preço AR |
| --- | ---: | ---: | ---: | ---: | ---: |
| Piso de 12,945 GB | 2,877 s | 7,381 s | 6,368 tok/s | 1,040 | +94,2 ms |
| Teto de 17,898 GB, cenário de sensibilidade | 3,977 s | 6,280 s | 7,484 tok/s | 0,573 | −1 006,4 ms |

O prompt, o decode e o primeiro final do mesmo pedido sem debug foram 10,784107 s, 9,858674 s e 20,385070 s. O crivo concede ao primeiro final toda a redução do decode, incluindo a cauda que acaba depois dele. Isso disponibiliza no máximo 10,257711 s para o novo prefill e o novo decode juntos. O preço médio AR hipotético é 9,858674/46 s. A nova trajetória exige 23 AR e 11 verificações. Se B3 custar uma AR, as 34 chamadas ocupariam 7,286846 s e deixariam **2,970865 s para o prefill completo**, equivalentes a **13,369 GB** se só houver leitura nessa fase. Nesse cenário, acima desse volume obrigatório o primeiro final já falharia mesmo com pesquisa, rollback e trabalho exposto de cálculo nulos. Operações sobrepostas só consomem a folga na medida em que alongarem o caminho crítico. [Hipóteses registadas antes da conta](protocol.md)

O relógio OFF pertence ao pedido original. Os IDs da nova conversa com debug reproduziram as mensagens, os eventos de escolhas e os denominadores, incluindo o histórico 2 044 + 153. A identidade individual dos IDs antigos e a sua distribuição de custos continuam em aberto. A fração dos bytes do processo efetivamente obrigatória nesse FD, a taxa útil por fase, a reposição de KV e o custo real de verificar três posições podem mudar a decisão. A comparação de custo precisa de R0 contemporâneo com as mesmas entradas, prefixo e recursos. [Recibo e precisão](evidence/receipt.json)

```sh
python3 -B research/qualification-retake/history_lookup/joint_budget/screen.py \
  --phases research/qualification-retake/nvme_conversation/phase_reads/evidence-r01/evidence.json \
  --b3 "$TESY_B3_SCREEN/receipt.json" --new-output-dir "$NOVO_DIRETORIO"
```
