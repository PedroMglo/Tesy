# Libertar o worker enquanto uma leitura está em voo

**Decode INCONCLUSIVE.** Os quatro braços C317 reconciliam a projeção bloqueante dos journals com quatro workers. A agenda temporal completa e os custos de serviço que regeriam a continuação ficam por identificar. Continuação favorável, sensibilidade e orçamento por continuação ficam `NOT_RUN`. O **NO_GO histórico de C318** mantém-se para o staging aprendido medido. R0 `slots40-persistent` é o controlo operacional. M3 PARTIAL e M4 NOT_MET. [Proveniência](proveniencia.md) · [Protocolo](protocolo.md) · [C317 corrigido](receipts/audit-mutex.json) · [C318](receipts/cost.json)

**Prefill NO_GO** para aplicar C262/R2 à chamada de 148 posições ou agrupar através do retorno 5→148. A alternativa que preserva a geometria tem recargas candidatas localizadas. A prova de capacidade, margem e paridade fica `NOT_RUN`. [DAG e limites](prefill.md)

## Decode C317

Conferiram os oito tamanhos e SHA-256, num total de 13 236 026 B. C317 trace-ON usa uma chamada nativa de prefill de 153 e 32 forwards fornecidos. Staging abre depois do prefill. O último marcador de chamada no primário precede o retorno de `prediction_finish`. Os 9,107–12,654 µs de cleanup vêm do relógio de fase do cliente histórico e pertencem ao decode. O nominal teve overhead mediano de 3,256% no decode perante limite de 3%. Os valores de C317 ficam no seu denominador diagnóstico. [C317](../C317-LEARNED-OBSERVER-RESULT-20261007.md) · [Cliente](../../tools/expert_learned_staging.cpp)

| C317 trace-ON | Gerações aceites/publicadas | Leitura direta | Anexos pronta / em leitura | Cancelados queued / ready / running | Esperas do router | Quatro trabalhos atribuídos / aceitações READING com outra procura na fila |
|---|---:|---:|---:|---:|---:|---:|
| nominal153-2 | 1 081 | 611 | 249 / 221 | 7 / 143 / 121 | 683 | 70 / 79 |
| nominal153-3 | 1 081 | 614 | 234 / 233 | 6 / 139 / 126 | 683 | 73 / 81 |
| code153-2 | 1 308 | 704 | 336 / 268 | 9 / 143 / 176 | 819 | 94 / 102 |
| code153-3 | 1 308 | 705 | 327 / 276 | 11 / 146 / 171 | 819 | 97 / 104 |

A projeção confirma 4 608 seleções autoritativas por braço. Cada miss tem um accept FIFO e uma publicação por geração, com três cópias de 4 406 400 B na ordem dos componentes. O destino fica reclamado de accept a publicação. Os `keep` da rota protegem as seleções. O buffer de staging conserva a posse até à cópia e release. Os números de substituições de forecasts em fila por leitura normal, fora da coluna dos cancelamentos, são 5/7 nominal e 8/9 código. Tickets emitidos terminam consumidos ou retirados. Leituras, bytes e estados terminais conferem com os contadores. Os 2/3/3/3 pedidos recusados por capacidade só têm contagem. As três, uma, zero e zero inversões adjacentes do primário são compatíveis com o índice atómico tomado antes do carimbo por threads concorrentes. Os carimbos de cada geração e os limites do seu router conferem. Da última espera explícita ao fim da chamada 32 passam ainda 5,23–5,26 ms no relógio primário. [Auditor](audit.py) · [Worker](../../patches/c305-cpu-prediction-staging.patch)

O algoritmo enumera os estados de prefixo alcançáveis das duas sequências e restringe-os aos que admitem chegar aos finais de ambas. Impõe capacidade e precedências de emissão, cancelamento, aceitação, cópia e publicação. Em qualquer intercalação admitida, os intervalos de ocupação podem ser atribuídos a quatro workers anónimos, reutilizando um worker quando o seu intervalo termina. O modelo deixa de fora a agenda do SO, partes sem instrumentação nas secções críticas, atrasos de despacho, arbitragem do dispositivo e custo concorrente. Cada journal mantém o seu relógio.

A revisão do mutex corrigiu a projeção do primeiro recibo. O worker mantém a mesma aquisição entre o accept primário e o anexo ao ticket. Todos os escritores do journal de staging precisam desse mutex. Por isso, ao aceitar, o prefixo de staging acaba exatamente um registo antes do anexo. No código-2, chamada 2 camada 6, ao accept primário 886 corresponde o prefixo staging 205, com uma procura e três produtores atribuídos. A contagem de ocupações lógicas passa a ser única nas 998 aceitações READING dos quatro braços. No controlo bloqueante há 334 observações com quatro trabalhos atribuídos e outra procura já na fila. A identidade física do worker, o seu despacho, o serviço por componente sob concorrência e a contribuição para a última barreira e o drain continuam por medir. [Demonstração e tabela por braço](revisao-mutex.md) · [Pré-registo da correção](protocolo-mutex.md) · [Primeiro recibo, com a precedência em falta](receipts/audit.json)

Em 133 dessas 334 observações, a cabeça FIFO podia iniciar uma leitura direta ou uma cópia READY. Em 201 esperava por outra leitura em curso. No próprio exemplo do código-2, a cabeça continuava em READING quando foi aceite. Estas contagens distinguem trabalho elegível numa única conversa. A duração que se poderia ganhar até à barreira continua desconhecida. [Tabela e verificador por braço](cabeca.md)

O envelope entre accept e primeira cópia soma 1,52–1,86 milhões de worker-µs. A união na parede é 1,45–1,79 s. A interseção com procura posteriormente aceite e WAIT do router é 0,46–0,58 s. Estes números localizam a sobreposição nesta execução. Libertar um worker pode deslocar trabalho que apareceria noutra janela ou deixar intacta a última dependência. A interseção não fornece um limite superior da melhoria. Também fica por identificar o custo máximo admissível em µs de parede por continuação. Sem um controlo temporizado reproduzido, a continuação não chega à fixture. [Critérios](protocolo.md)

## C318 trace-OFF

Os oito recibos confirmam a ordem ABBA, os relógios, os digests da matriz completa de 33 linhas de logits e os ganhos publicados. O custo fixado inclui predictor, cópias, cancelamentos e cleanup. O prefixo fica fora do total. Cada par usa o seu R0 como denominador.

| Caso e par | Prefill R0 → B (s) | Decode R0 → B (s) | Total R0 → B (s) | Ganho total | Ganho decode |
|---|---:|---:|---:|---:|---:|
| nominal AB | 9,691 → 9,756 | 9,450 → 9,708 | 19,141 → 19,464 | −1,69% | −2,73% |
| nominal BA | 9,663 → 9,710 | 9,397 → 9,737 | 19,060 → 19,447 | −2,03% | −3,62% |
| código AB | 15,813 → 15,752 | 10,974 → 11,403 | 26,787 → 27,155 | −1,37% | −3,91% |
| código BA | 15,749 → 17,174 | 11,785 → 12,193 | 27,534 → 29,367 | −6,66% | −3,46% |

| Caso | Redução em B pela via de +8% total | Via de +15% decode | Segundos em AB / BA pela via de +15% | Via de fase +10% decode |
|---|---:|---:|---:|---:|
| nominal | 19,36% | 17,62% | 1,710 / 1,715 | 12,77% |
| código | 27,67% | 18,02% | 2,055 / 2,197 | 13,20% |

Os limiares mantêm o prefill e aplicam a mesma redução proporcional ao decode dos dois B do caso. O prefill fixo respeita a proteção da via de fase com medianas de −0,57% nominal e −4,33% em código. Verificam-se também o sinal de cada par, o total mediano e a proteção do outro caso. Se o outro caso ficar no resultado histórico, a mediana do seu total supera −5% (−1,86% nominal, −4,01% código). Se for afetado, a folga nessa proteção equivale a uma desaceleração uniforme do decode candidato de até 6,17% nominal ou 2,27% código. Esta é folga no denominador histórico da proteção. O custo da continuação permanece desconhecido. [Cálculo](cost.py) · [Recibo](receipts/cost.json) · [Avaliador original](../../tools/expert_staging_product_cost_gate.py)

## Reproduzir

A partir da raiz, com os caminhos locais fornecidos no ambiente. Cada destino tem de ser novo.

```sh
python3 research/consolidacao-20261123/verify.py
python3 research/post-c320/analyse.py
python3 research/post-c320/analyse.py --raw-dir "$TESY_C317_RAW"
out=$(mktemp -d)
python3 research/worker-release-20261124/audit.py --raw-dir "$TESY_C317_RAW" --output-dir "$out/blocking"
python3 research/worker-release-20261124/head.py --raw-dir "$TESY_C317_RAW" --new-output-dir "$out/head"
python3 research/worker-release-20261124/cost.py --output "$out/cost.json"
python3 research/worker-release-20261124/prefill.py --trace "$TESY_C135_TRACE" --output "$out/prefill.json"
python3 -m unittest discover -s research/worker-release-20261124
```

O clone completo confirmou 45 heads, duas raízes e quatro árvores de arquivo. A primeira tentativa do auditor interpretou o campo `staging.enabled` como estado final, quando o cliente grava aí a política do braço. O campo `idle` testemunha a drenagem. A correção precedeu a repetição em diretório novo e o FAIL preliminar fica preservado localmente. A CI usa a projeção abstrata e os recibos Git. Pontos de revisão do Pedro: identificabilidade da agenda, alcance causal das recargas de prefill e aplicação dos gates C318.
