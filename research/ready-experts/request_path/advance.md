# O que faria reabrir a decisão de backend?

**NO_GO para antecipar pesos repetindo a última rota desta mesma camada, neste perfil.** A regra só identificou 42 faltas em visitas repetidas e oferecemos-lhe ainda 37 acertos de entrada. Mesmo pagando zero por previsões erradas e creditando uma camada inteira sempre que acertava num único expert, o primeiro conteúdo final levaria **10,308–10,406 s em P97 e 11,410–11,510 s em P106**. O crédito antes do primeiro final veio integralmente do prefill. Nos 44 avanços seguintes não houve crédito de parede. [Pré-registo](advance-protocol.md) · [Certificado dos grupos e dos quatro cortes](evidence-advance-20261128-r01/decision.json)

| Braço do NVMe | Journal | Défice de primeiro final, s | Mínimo de grupos com serviço adiantado | Crédito dos melhores N−1, s | Crédito dos melhores N, s |
|---|---|---:|---:|---:|---:|
| 1 | P97 | 0,851 | 31 | 0,848 | 0,867 |
| 4 | P97 | 0,990 | 33 | 0,973 | 0,992 |
| 1 | P106 | 1,941 | 119 | 1,940 | 1,950 |
| 4 | P106 | 2,085 | **122** | 2,082 | 2,092 |

Cada grupo é uma visita a camada com pelo menos uma falta obrigatória. A prova ordena o tempo de leitura que ainda fica exposto depois de oferecer até ao router seguinte para o esconder. O crédito máximo de N grupos é a soma dos N maiores excessos, pois os intervalos são disjuntos. Em cada linha o decode já satisfaz o limiar na projeção favorável. O oráculo escolhe grupos diferentes por linha, elimina a dívida inteira de cada escolhido e oferece movimento de bytes, capacidade, sincronização e erros. Logo, 122 é uma condição necessária para uma solução que só adiante estes grupos no corte mais exigente. Uma política realizável terá de servir os mesmos bytes corretos a tempo e pagar as consequências das escolhas nas restantes camadas.

**Decisão de engenharia.** Conservar R0 e os componentes com ganhos integrados medidos. Uma proposta que atravesse camadas pode justificar um executor estreito se obtiver informação causal anterior e demonstrar crédito líquido superior a **2,085 s** no corte P106 mais exigente, conservando os outros três cortes e o caso de código. A condição também pode mudar se outra disposição reduzir os bytes obrigatórios ou o custo de cálculo exterior. A tarefa de código precisa de uma observação equivalente para avaliar esse mecanismo. A utilidade multiutilizador e outros perfis de hardware exigem contratos próprios. [Resultados físicos e controlos do produto](../cpu_wave/code_chat/README.md)

```sh
p=research/ready-experts/request_path
python3 -IB "$p/advance.py" --check "$p/evidence-advance-20261128-r01"
```
