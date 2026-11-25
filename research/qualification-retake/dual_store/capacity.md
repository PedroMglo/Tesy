# Duas cópias do GGUF e os orçamentos de C135 e C294

**NO_GO condicionado para o prefill C135 com os mesmos misses e decode a exatamente 6 tok/s.** Neste pedido seriam necessários **6,656 GB/s úteis** mesmo que a leitura ocupasse todo o orçamento do prefill. Conceder simultaneamente 4,5 GB/s úteis no SSD interno e todos os 1,25 GB/s brutos do USB dá 5,75 GB/s. A diferença é 0,906 GB/s. A retenção a partir do estado de entrada observado e os 32 passos de C294 têm condições diferentes e merecem contas próprias. [Prefill e relógio cliente C135](../prefill_read_floor/README.md) · [Conclusões por fase no USB](../usb_prefill.md)

## O que significa somar 4,5 e 1,25

As duas cópias verificadas têm 63 387 346 208 B e o mesmo SHA-256. O endpoint USB negociado a 10 Gbit/s limita o transporte device→host a **no máximo 1,25 GB/s** brutos, mesmo em caso de hit no controlador. O Micron 2400 de 1 TB tem uma especificação de 4 500 MB/s de leitura sequencial a 128 KB, QD32, com a unidade nova. Nesta conta 4,5 GB/s é um **cenário** para o payload útil do NVMe. O enlace e a ficha estabelecem condições de naturezas diferentes. [Colocação e integridade](../nvme_placement/README.md) · [USB observado](../usb.md) · [Método da Micron](https://www.micron.com/content/dam/micron/global/public/products/product-flyer/2400-ssd-product-brief.pdf)

Se cada byte necessário puder vir de qualquer cópia, sem duplicação, com partição contínua perfeita, e as fontes sustentarem em paralelo as taxas úteis N e U, B bytes exigem pelo menos B/(N+U) segundos. A igualdade concede divisão de uma componente, nenhuma cauda por camada, zero latência, zero alinhamento, zero contenção de barramentos, quatro workers sempre prontos e nenhuma perda até à última publicação. A soma dos limites individuais continua válida quando estas concessões falham, mas a igualdade deixa de estar garantida. Uma carga lógica tem 13 219 200 B. Todo o quadro usa GB decimais. [Geometria e contadores](../usb.md)

## Primeiro conteúdo no segundo pedido natural C135

O prefill de 5+148 fez 45+1 177 admissões, por 16 153 862 400 B. Para esta trajetória de 47 saídas, conceder a poupança **inteira** de passar ao decode a exatamente 6 tok/s antes do primeiro conteúdo deixa 2,427104 s de prefill no próprio relógio C135. A tabela dá pisos de transporte e folgas máximas para o restante caminho crítico descoberto.

| Cargas na fase 5+148 | GB | N+U necessário (GB/s) | N mínimo se U=1,25 | U mínimo se N=4,5 | Piso a 5,75 (s) | Folga (s) |
|---|---:|---:|---:|---:|---:|---:|
| R0 observado, 1 222 | 16,153862 | 6,655611 | 5,405611 | 2,155611 | 2,809367 | −0,382263 |
| Conceder a eliminação das 184 recargas identificadas, 1 038 | 13,721530 | 5,653457 | 4,403457 | 1,153457 | 2,386353 | +0,040751 |
| Piso com entrada histórica e 40 slots/camada, 874 | 11,553581 | 4,760232 | 3,510232 | 0,260232 | 2,009318 | +0,417786 |

No cenário combinado cabem no máximo **1 055 cargas** inteiras. Com os mesmos bytes faltam 2,198 GB, ou **167 cargas** a evitar. Alternativamente, atribuindo todo o crédito de decode ao primeiro conteúdo, o próprio C135 precisaria de pelo menos **6,308 tok/s** mesmo com o prefill reduzido ao puro transporte desses bytes. A conta usa `47/(47/6 − 0,382263)`. Há 16 slots iniciais cujo conteúdo só é parcialmente conhecido. Os 874 são um piso com o futuro disponível e a reconstituição final gratuita. Uma política causal que parta da entrada real teria de demonstrar um número entre esse piso e as 1 055 cargas admissíveis, e pagar as outras operações. A hipótese de eliminar 184 em simultâneo também continua uma concessão. [Piso por camada e entradas identificadas](../prefill_entry40/README.md) · [Recargas observadas](../usb_prefill.md)

## Trinta e dois passos fornecidos em C294

Para estes braços, 32/6 dá 5,333333 s. Com todos os outros trabalhos gratuitos, os mesmos misses exigem 2,679367 GB/s no nominal e 3,242009 GB/s em código. Se fosse possível conservar todos os experts depois da sua primeira procura, partindo da mesma cache I, seriam obrigatórios 779 e 928 experts distintos, ou 1,930829 e 2,300141 GB/s de payload útil. Com 40 slots por camada, a melhor escolha de vítimas conhecida com antecedência deixa **787 e 928** cargas. O aumento de capacidade só beneficia o nominal em oito cargas neste limite. [Limites com o estado I fixo](../cache.md)

Uma condição mais exigente conserva F, a duração histórica fora das esperas de serviço no próprio braço C295. Concede as duas fontes para ler as faltas de cada camada após o router; todas as transferências físicas de pesos ficam nas janelas de serviço. O overlap com F é zero neste cenário. No journal todos os READs das primeiras faltas obrigatórias ficaram dentro das respetivas esperas. Se a nova arquitetura antecipar bytes durante F, o primeiro cálculo com todo o resto gratuito continua aplicável, e a sobreposição nova precisa de testemunho ao nível do pedido. O restante medido em cada caso aparece uma única vez. A taxa mínima com F fixo é B/(32/6−F). [Restante C295 e isolamento das leituras](../primary_backing/README.md) · [Quatro controlos de serviço](../component_ready_bound/README.md)

| C294 trace-ON | F (s) | Cargas R0 / retenção ilimitada | GB/s necessários com F, R0 / retenção | Piso F+B/5,75 (s), R0 / retenção | Folga máxima (s), R0 / retenção |
|---|---:|---:|---:|---:|---:|
| nominal153-2 | 1,773408 | 1 081 / 779 | 4,014 / 2,893 | 4,259 / 3,564 | 1,075 / 1,769 |
| nominal153-3 | 1,830919 | 1 081 / 779 | 4,080 / 2,940 | 4,316 / 3,622 | 1,017 / 1,712 |
| code153-2 | 1,817114 | 1 308 / 928 | 4,917 / 3,489 | 4,824 / 3,951 | 0,509 / 1,383 |
| code153-3 | 1,829011 | 1 308 / 928 | 4,934 / 3,501 | 4,836 / 3,962 | 0,497 / 1,371 |

Para preservar os misses em código sob F fixo, mesmo que o NVMe entregue 4,5 GB/s úteis, o USB precisa de contribuir pelo menos **0,417 / 0,434 GB/s** enquanto se serve o trabalho. A retenção ideal com I fixo põe ambos os casos abaixo da taxa de cenário do próprio NVMe. A dificuldade continua na latência e ocupação por camada, no cálculo, nas admissões efetivamente evitadas e na materialização dos residentes. C295 já confirmou que a retenção primária ilimitada sob as durações históricas de READ, até reduzidas a 80%, falha em todos os braços com o restante fixo. Uma taxa agregada não demonstra que os tempos das barreiras tenham mudado na proporção necessária. [Serviço histórico por barreira](../primary_backing/README.md)

## Decisão de investimento

As contas dispensam uma nova leitura física para rejeitar **somente a segunda fonte como via suficiente para C135 com tráfego inalterado, decode a 6 e o cenário de banda indicado**. Reabriria com evidência simultânea de N+U≥6,656 GB/s úteis, decode efetivamente mais rápido ou menos cargas. A combinação com retenção continua **INCONCLUSIVE** até existir uma agenda causal que respeite a entrada e as duas saídas externas, cobre os bytes de preparação/primeiro decode e deixe tempo para o resto do pedido. O mínimo 874 só deixaria 417,8 ms nas condições ideais.

Nos braços C294 os pisos de bytes deixam margem matemática. Uma medição de leitura a dois discos só distingue essa via se comparar uma atribuição implementável dos mesmos offsets e quatro workers com o NVMe isolado, por barreira autoritativa, e cobrar a última publicação, cópia e coordenação. O ensaio publicado sobre a primeira posição C135 já comparou separadamente os dois discos nos mesmos 20 misses de 16 camadas. Mede 145,4–145,5 ms no NVMe e 493,4–498,3 ms no USB; somar débitos ou escalar esses tempos a outras posições não observa serviço simultâneo. A prioridade é verificar que a atribuição e a política de residência deixam margem nos dois workloads antes de gastar uma janela física. Nenhum valor C135 foi transferido para o cliente C281; seis passos/s em código é um limiar comum de triagem dos trabalhos fornecidos. M3 PARTIAL e M4 NOT_MET. [Amostra de primeira posição](../nvme_admission/README.md) · [Controlo cliente contemporâneo](../nvme_conversation/README.md)

**Proveniência.** Aritmética sobre recibos publicados, sem novos raws, pesos, GPU, forwards ou I/O dos modelos. O recibo C135 dos payloads tem SHA-256 `624dd4b64a045ae9237d581a13d453415b79e21879d8ec16c638f596781dfa1d`, o do piso de entrada `16291c82a97afeb320d537e7be81dddf8833b583add98ffcf868666dd1ce4901` e o da retenção C294/C295 `44ba456b19a1d4fcd44ecb7127a99db410344e304a4e51474d41dec1847fc9f5`.
