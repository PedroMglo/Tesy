# O bloco de três posições reproduziu o decode serial do 120B nos cortes verificados

**GO para testar rejeição e continuação.** Com o GPT-OSS-120B MXFP4 original no NVMe interno e a RTX 4060 Laptop, um só grafo para três posições reproduziu todos os cinco vetores completos de logits, as 1 185 ativações observadas, os 108 quartetos ordenados e o KV da execução serial. A continuação de uma posição também produziu os mesmos 201 088 logits. O caso tem 189 posições de prefixo e IDs fornecidos. A medição de custo por token confirmado e a conversa natural com rollback estão por executar. [Resultados por braço](result.json) · [Pré-registo](protocol.md)

| Contrato contra a referência serial independente | BASE | Só down em L25 | Atenção e down em L25–35 |
|---|---:|---:|---:|
| Primeiro corte observado com diferença | FFN L25 | Logits do router L26 | Todos iguais |
| FFN L25, F32 diferentes em 189 / 190 / 191 | 33 / 29 / 109 | 0 / 0 / 0 | 0 / 0 / 0 |
| Ativações iguais, de 1 185 | 1 090 | 1 093 | 1 185 |
| Quartetos top-4 ordenados diferentes, de 108 | 2 | 2 | 0 |
| Palavras F16 de KV pós-bloco diferentes, de 5 898 240 | 26 887 | 26 887 | 0 |
| Vetores completos de logits iguais, de 5 | 1 | 1 | 5 |
| Tokens greedy únicos iguais, de 5 | 5 | 5 | 5 |

Os três braços conservaram os 2 248 ficheiros do prefill e os estados iniciais de KV e dos 40 slots. BASE reproduziu a árvore inteira da parte 167, inclusive a geometria e as 1 185 capturas. Em D25, a saída dos experts ficou exata. O primeiro corte observado em L26 já diferia nos 128 logits do router em cada posição. Nos dois primeiros braços, o último vetor do prefill era o único bit a bit igual. Em CUDA, as 1 005 440 palavras F32 dos cinco vetores coincidiram. As máscaras de L25 conservaram as 190, 191 e 192 posições visíveis. O runtime construiu os cortes por linha com a máscara nativa de cada camada e 256 células nos onze casos. A experiência demonstra a suficiência desta combinação para este bloco. A contribuição marginal de cada uma das dez camadas seguintes ficou por isolar. [Grafo e checks de colocação](build.py) · [Executor e critérios](family.py)

| Recursos físicos | BASE | D25 | CUDA |
|---|---:|---:|---:|
| Processo com observador / scope incluindo C118, s | 28,484 / 89,225 | 28,440 / 89,232 | 28,307 / 88,978 |
| Pico de cgroup, B | 15 860 117 504 | 15 946 203 136 | 15 849 500 672 |
| Pico da RTX, MiB / swap do cgroup, B | 6 868 / 0 | 6 868 / 0 | 6 868 / 0 |
| Energia estimada da GPU, J / cobertura, s | 333,4 / 27,783 | 330,1 / 27,736 | 336,0 / 27,616 |

Cada braço teve 61 amostras de C118 e 109 observações do mapa nativo. Três arranques do modelo, zero pedidos HTTP. Máximos de 72,5 °C na CPU, 52,73 °C na GPU e 48,85 °C no NVMe. A energia total do portátil é desconhecida. Os tempos incluem a instrumentação. O protocolo está em `90e19c5c`, a biblioteca em `11d64665` e a medição em `e73ba797`. O revisor dos originais e o dos 10 400 ficheiros privados deram o mesmo SHA-256 `4cf9fa1a34d26e481484c19f6627baf14c1aa29cb985cd10037eec50fc6df092`. [Revisor sem modelo nem GPU](review.py) · [Manifesto privado](../../../../../../../../private_archive/part-169.json)

O melhor pedido nominal emparelhado com pack mantém 18,313 s até ao primeiro conteúdo final e 5,361 tok/s. Sob o cenário que atribui ao cliente toda a poupança do decode, chegar exatamente a 6 tok/s deixaria 7,379 e 7,417 s por recuperar nas duas ordens. O histórico natural C281 teve cinco blocos com rejeição da primeira proposta e seis com aceitação de duas. O próximo teste deve reconstruir o KV após uma rejeição e verificar o token confirmado e a continuação contra AR. M3 PARTIAL, M4 NOT_MET. [Orçamento por pedido](../../../../../../../../packed_nvme_manifest/server_profile/conversation/decode_budget.md) · [Propostas observadas](../../../../../../../../history_lookup/native_ids/b3_fixture/README.md)
