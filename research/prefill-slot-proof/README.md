# Pode uma recarga de prefill desaparecer do caminho crítico do pedido?

**NO_GO condicionado para antecipar a cópia para o destino fixo de R0.** No C135, até a união de 119 recargas individualmente possíveis fica limitada a **0,984452 s** de alívio, com cópia e coordenação gratuitas, pelo modelo de quatro workers abaixo. O screen histórico de 10% exige **1,1702723 s** no prefill de 5+148. Uma agenda conjunta de 53 recargas preserva o payload por slot até ao primeiro decode. Para mudar de vítima há mais margem em contagem de cargas e o efeito no relógio do pedido continua **INCONCLUSIVE**. [Protocolo congelado](protocol.md) · [Recibo por cenário](evidence/receipt.json) · [Políticas de vítima](victims.md) · [Triagem da wave corrente](observation.md)

### Qual pedido e qual relógio

A base desta unidade é a head do #44. A auditoria dos oito originais C317 e dos oito braços de custo C318 fica naquela unidade. Decode C317 INCONCLUSIVE, continuação NOT_RUN e staging C318 NO_GO. Os cortes condicionais de 17,62% nominal e 18,02% código pertencem ao decode do candidato C318 pela via de +15%. O atual screen usa o C135 nominal trace-ON e uma única observação. O recibo C261 dá 11,702723 s para os dois retornos de prefill. O journal cobre 11,205722 s na chamada de 148. Preservámos os denominadores e a fronteira de cleanup do respetivo protocolo. Os sinais dos pares AB e BA, o caso de código e a proteção da outra fase exigem medições emparelhadas trace-OFF no avaliador. [C317/C318 e avaliador](../worker-release-20261124/README.md) · [C261](../C261-SLOTS40-PREFILL-OPPORTUNITY-20261004.md)

No pedido natural C136 trace-OFF, retirar todo o decode deixa **10,665 s** até ao primeiro conteúdo final. Retirar todo o prefill deixa cerca de **9,965 s** se o restante trabalho mantiver o tempo observado. Restariam cerca de 35 ms para o prefill atingir o alvo nominal nessa hipótese. Para 47 tokens, chegar a 6 tok/s exigiria ainda reduzir o decode de 10,206 s para 7,833 s. Esta aritmética explica a decisão de investigar mais de uma fase. R0 `slots40-persistent` opt-in, M3 PARTIAL, M4 NOT_MET. C133 terminou naturalmente 20/20, com 19/20 no validador. [C135/C136](../C135-C136-SLOTS40-RESIDUAL-DECODE-20260929.md) · [Contratos operacionais](../post-c320/README.md)

### Uma agenda conjunta com 40 slots por camada

O router, KV, atenção, top-4 e redução continuam nos tiles 32+32+32+32+20 da chamada de 148, após o retorno de 5. Mantêm-se as vistas, pesos MXFP4, biases, ranks, ordem das waves e os tensores do backend. Onde se aplica o preload, a wave usa até 18 experts, mais o parking e a wave seguinte. A posição física do parking e os IDs por token incompletos do trace levam a excluir todo o tile tocado por um possível consumidor do deslocado. O verificador herda a validade da aritmética do grafo apenas como premissa para a projeção. A prova executada compara identidades dos três componentes e gerações no serviço de slots. [DAG e pin C281](../worker-release-20261124/prefill.md) · [Replay independente](verify_slots.py)

Quando R0 vai expulsar X da slot i, a agenda copia gate, up e down para a slot j no mesmo tier. O residente Z de j tem de estar READY e livre de consumidores e escritores até à admissão futura de X. A leitura anterior de Z precisa de ter terminado e a cópia de X tem de acabar antes da reutilização de i. O controlador mantém a política de R0 em sombra, valida a geração e publica X no ponto da admissão original. Qualquer previsão online precisaria de detetar uma procura inesperada de Z, fornecer os bytes exatos antes do consumidor e cobrar a recuperação. A agenda apresentada dispõe dos pedidos futuros. Os 19 e 2 mínimos de capacidade CPU/CUDA determinados por C261 são admissões obrigatórias.

| Partição das 184 recargas entre tiles | Número |
|---|---:|
| Destino igual à origem com sobrescrita, ou escrita intermédia no destino | 49 |
| Procura histórica de Z dentro do empréstimo | 16 |
| Destino sem testemunha READY suficientemente cedo | 37 |
| Z com consumo ou parking possível num tile tocado | 29 |
| Agendadas em conjunto e verificadas | **53** |

Entre as 119 que passam as duas condições necessárias, até 104 têm extremos mutuamente distintos. O limite temporal concede as 119 em simultâneo. A testemunha conservadora liga **31 cargas CPU e 22 CUDA** aos pares de evicções publicados. O replay valida reserva, enqueue, dequeue, três transações read/set e publicação, sem sobreposição de posse. Contabiliza 409 795 200 B CPU e 290 822 400 B CUDA de leitura lógica evitada e o mesmo payload em cópia adicional local. As duas extremidades das cópias movimentariam pelo menos 1 401 235 200 B de leitura+escrita agregada com essa implementação. Tráfego físico NVMe/PCIe, RAM e VRAM fica DESCONHECIDO. Na fronteira 148 e após o primeiro decode, todos os payloads simbólicos coincidem por slot. Slots iniciais nunca identificados são a mesma incógnita nas duas execuções. O primeiro decode conserva as 144 procuras e as 20 cargas originais, repartidas em 17 CPU e 3 CUDA. [Seletor](select_slots.py) · [Certificado com os pares de eventos](evidence/receipt.json)

### Tempo atribuível

| C135, hipótese sobre as recargas removidas | Esperas afetadas / última dependência removida | Alívio direto com outras publicações fixas (s) | Teto com quatro workers e releases por wave (s) | Teto com releases e deadlines de consumo (s) |
|---|---:|---:|---:|---:|
| 184, até sem restrição de destino | 94 / 45 | 0,214562–0,333667 | 1,614516 | 1,367310 |
| União relaxada de 119 com destino fixo | 71 / 29 | 0,131879–0,218777 | 1,218549 | **0,984452** |
| Agenda conjunta de 53 | 40 / 11 | 0,088123–0,098824 | 0,629844 | **0,514192** |

Há 222 esperas, totalizando 7,556772 s. Um exemplo mostra por que o total de WAIT associado a um candidato sobrestima a poupança. Na camada 12 do segundo tile, a espera dura 39 441 µs. O worker do expert 93 entrega o bloco 8745, mas o consumidor precisa ainda do expert 124, bloco 8759. O carimbo LOAD_END é colhido antes da publicação. A ordem sob o mutex, o último carimbo já amostrado e o próximo carimbo protegido delimitam a publicação. A coluna direta mantém o custo de despertar quando resta uma dependência e oferece toda a espera quando desaparecem todas. [Atribuição das barreiras](critical.py)

O último teto concede despacho ideal, quatro workers e serviço de cada geração retida pelo menos igual à sua duração observada, descontada a resolução do relógio. Em cada par (tile, camada), cada serviço liga o primeiro enqueue ao consumidor da sua wave. Para cada intervalo de release a deadline, o trabalho inteiramente contido exige pelo menos a soma das durações dividida por quatro. O caminho mais longo das restrições, incluindo o trabalho do controlador fora de WAIT, dá um mínimo de duração e portanto um máximo de alívio. O verificador exige que todas as gerações encerradas nesse âmbito tenham consumidor e que o mínimo caiba no relógio observado. Presume-se que libertar capacidade num âmbito não muda o serviço de outro. As 184 excedem o corte apenas como teto relaxado, sem agenda demonstrada. [Limite por intervalo e fixtures](critical_intervals.py)

Se todo o tempo observado dentro dos callbacks também for grátis, os tetos tornam-se 1,368083 / **0,984950** / 0,514498 s. Faltam **185,3223 ms** à união de destino fixo, mesmo nesta sensibilidade. O custo admissível adicional para atingir +10% já é negativo. Para os 53, cobrar, no caminho crítico, cópias CPU/CUDA, fence do último consumidor, retenção de i, custo de despacho e publicação. Se tudo serializar, o termo de payload é 409795200/B_CPU + 290822400/B_CUDA segundos para taxas de cópia em B/s. A reposição final de payload desta agenda custa zero cópias adicionais. Uma redução demonstrável do serviço remanescente por menor contenção, ou trabalho adiantado através de camadas, mudaria a premissa do teto. Paridade de KV/máscaras, logits completos finitos, IDs, energia, TTFT e ganho cliente da intervenção ficam NOT_RUN.

### Memória viva

Para a cópia no destino, o grafo do target tem exatamente os mesmos tensores vivos em cada instante da sua agenda lógica. O incremento de workspace de ativações é **0 B CPU e 0 B CUDA** no plano que copia diretamente entre as duas slots. Reservar dois `uint64_t` por slot para destino e geração custaria 23 040 B no host e 0 no dispositivo. Uma implementação que precise de staging ou de um novo stream tem de recalcular o pico e medir fences. O stderr R0 histórico C280 regista arenas compute reservadas de **8,1810 MiB CUDA_Host e 25,2500 MiB CUDA0**, output 0,77 MiB e KV 400 MiB CPU / 176 MiB GPU. Os quatro buffers de componente ocupam 17 658 368 B no host. São reservas e dimensões históricas com lifetimes diferentes. O high-water mark individual de ativações no C135 permanece desconhecido. [Manifesto do stderr C280, 140 205 B, SHA 1fb1ca08…](../../results/c280-r2-three-way-causal-cost-20261005/raw-manifest.json)

Uma agenda alternativa que materialize várias camadas ou tiles precisa de outro cálculo. Por exemplo, três fronteiras F32 de 148×2880, quatro contribuições por posição e duas matrizes top-4 somam 11 939 456 B no tier ativo se coexistirem. Transportar o residual entre tiers custa 1 704 960 B por travessia. O pico total dependerá da alocação e do reuso de buffers de atenção/KV e workspace do backend. Para reabrir essa via, construir as vistas originais numa fixture, manter as duas fronteiras externas e comparar cada redução, KV, máscara, logits finitos e IDs ao R0 independente antes de admitir timing. A ablação preservaria a agenda candidata e desligaria só o reuso. [DAG e referência independente](../worker-release-20261124/prefill.md)

### Reproduzir no clone completo

```sh
python3 research/consolidacao-20261123/verify.py
python3 research/post-c320/analyse.py
python3 -m unittest discover -s research/prefill-slot-proof
python3 research/prefill-slot-proof/study.py --trace "$TESY_C135_TRACE" --new-output-dir "$NOVO_DESTINO"
```

Os comandos do oracle e da triagem das 79 cargas usam a mesma opção de trace e um diretório novo por execução, trocando `study.py` por `oracle.py` ou `current_wave.py`. [Proveniência e custo](proveniencia.md)

O congelamento foi feito na base e7a659db, main 293f5b18. O analisador exige o hash C135 de C261 e verifica schema, tiles e calls. O recibo inclui o digest do protocolo, o hash do trace e os índices do certificado. O destino é exclusivo, com publicação por rename e FAIL local em caso de erro. O trace e os prompts permanecem no portátil. A CI corre apenas fixtures sem modelo. [Antecedentes e data de corte](literatura.md)
