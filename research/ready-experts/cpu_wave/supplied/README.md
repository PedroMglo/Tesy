# Quanto ganharia o utilizador com outro backend?

**NO_GO para uma reescrita do executor de cálculo como solução para o primeiro conteúdo final neste portátil.** Com o serviço atual de pesos, até tornar gratuitos CPU e GPU deixa o cliente acima de 10 s nos dois traces. O primeiro alvo continua o GPT-OSS-120B MXFP4 original com histórico e contexto 8192. R0 `slots40-persistent` é o controlo operacional, M3 PARTIAL e M4 NOT_MET. A decisão sobre arquiteturas que mudam a disponibilidade dos pesos tem um teste separado abaixo. [Contrato do perfil](../../../../docs/architecture/0005-execucao-local-por-perfil.md)

## O que já entrega o backend existente

**MEDIDO no portátil, GO_SUPPLIED_COMBINATION.** Em nominal e código, a combinação do pack C291 com a fusão de waves CPU reduziu o tempo para trabalho idêntico em **11,39% e 13,20%**, mediana dos dois pares contra R0 independente. O avaliador C293 comparou também a combinação com a mesma biblioteca em transporte GGUF. A fusão acrescentou 3,08% / 2,73% de redução mediana do prefill com o pack já instalado. Os contrastes abaixo mostram o sinal de cada par no total. [Critérios, ordem e relógios](protocol.md) · [Braços, pares por fase e telemetria](decision.json)

Cada caso tem oito processos independentes. R é o R0 C269 com o cliente C280. G usa C291 e a biblioteca CPU PRICE desligada, com os offsets do GGUF. P junta as três matrizes originais por expert no pack, com a fusão desligada. W ativa a fusão no mesmo binário e pack. A cache de páginas do sistema evolui entre processos. A fixture avalia um prefixo completo de 2 044 / 1 952 IDs e drena os pools. O total da tabela soma a chamada incremental de 153 IDs (32+32+32+32+25) e 32 passos de um ID fornecido. Os relógios incluem recolha dos logits e argmax, e terminam antes do drain e da escrita finais. O scope inclui a admissão, toda a execução e o encerramento. Os 32 passos têm trabalho fixo e servem para atribuição de custo. A conversa natural e o C318 com cleanup têm relógios próprios.

| Caso | Ordem | Prefixo (s) | Prefill 153 (s) | Decode 32 (s) | Total (s) | Scope (s) |
|---|---|---:|---:|---:|---:|---:|
| nominal153 | 1R | 62,207 | 9,320 | 9,017 | 18,337 | 144,241 |
| nominal153 | 2G | 62,301 | 9,277 | 8,988 | 18,265 | 144,471 |
| nominal153 | 3P | 59,431 | 8,460 | 8,061 | 16,521 | 139,470 |
| nominal153 | 4W | 54,319 | 8,157 | 8,153 | 16,310 | 134,428 |
| nominal153 | 5W | 54,356 | 8,272 | 8,141 | 16,412 | 134,373 |
| nominal153 | 6P | 59,040 | 8,491 | 8,029 | 16,520 | 139,214 |
| nominal153 | 7G | 62,882 | 9,259 | 9,018 | 18,277 | 144,987 |
| nominal153 | 8R | 62,251 | 9,249 | 9,341 | 18,590 | 144,497 |
| code153 | 1R | 58,067 | 14,679 | 10,454 | 25,133 | 146,520 |
| code153 | 2G | 57,043 | 14,913 | 10,482 | 25,396 | 146,002 |
| code153 | 3P | 54,391 | 12,779 | 9,409 | 22,188 | 140,166 |
| code153 | 4W | 49,913 | 12,399 | 9,433 | 21,832 | 135,126 |
| code153 | 5W | 50,116 | 12,565 | 9,401 | 21,966 | 135,611 |
| code153 | 6P | 54,868 | 12,885 | 9,492 | 22,377 | 140,911 |
| code153 | 7G | 57,434 | 14,964 | 10,478 | 25,442 | 146,223 |
| code153 | 8R | 57,454 | 14,848 | 10,475 | 25,324 | 146,190 |

| Controlo → candidato | Caso | Ganho total por par (%) | Mediana total (%) | Mediana prefill (%) | Mediana decode (%) |
|---|---|---:|---:|---:|---:|
| R/W | nominal153 | 11,06 / 11,72 | 11,39 | 11,52 | 11,22 |
| R/W | code153 | 13,13 / 13,26 | 13,20 | 15,45 | 10,02 |
| G/W | nominal153 | 10,70 / 10,20 | 10,45 | 11,37 | 9,51 |
| G/W | code153 | 14,03 / 13,67 | 13,85 | 16,44 | 10,15 |
| G/P | nominal153 | 9,55 / 9,61 | 9,58 | 8,55 | 10,64 |
| G/P | code153 | 12,63 / 12,05 | 12,34 | 14,10 | 9,83 |
| P/W | nominal153 | 1,28 / 0,65 | 0,97 | 3,08 | -1,26 |
| P/W | code153 | 1,60 / 1,84 | 1,72 | 2,73 | 0,35 |
| R/G | nominal153 | 0,39 / 1,69 | 1,04 | 0,18 | 1,89 |
| R/G | code153 | -1,04 / -0,47 | -0,76 | -1,19 | -0,15 |

**Exatidão.** Os 16 processos deram as mesmas 33 linhas de 201 088 logits F32 finitos e os mesmos IDs que os dois controlos C280 independentes de cada caso. Foram 528 linhas físicas. A comparação bitwise usa o SHA-256 por caso. O mesmo estado determinístico drenado dos 36 pools e as mesmas gerações de carga reapareceram nos dois cortes. No intervalo fornecido, cada processo teve 1 486 cargas CPU e 638 GPU no nominal, 2 595 CPU e 819 GPU em código. O contador nativo da store em P/W inclui o prefixo inteiro, dando 5 694 / 6 433 cargas completas de 13 219 200 B. São bytes lógicos de pesos. A fixture observa os logits, argmax e pools e não recolhe todos os IDs internos do router.

**Recursos e repetição.** Ryzen AI 9 HX 370, RTX 4060 Laptop, driver 620.73.04, AC, perfil performance, modelo no NVMe interno em Btrfs, 8 threads, GPU12, 40 slots, 4 workers, contexto 8192, ub32 e uma sequência. As famílias completas demoraram 18,89 min no nominal e 19,03 min em código, incluindo as admissões. Pico de cgroup 14,84 GiB e swap 0 B. O contador de utilização da placa chegou a 6866 MiB. Máximos CPU/GPU/NVMe 95,50 / 65,12 / 54,85 °C. A integração da potência amostrada da placa estima 18,42 kJ em 1278,3 de 1289,6 s monitorizados. Energia total à tomada desconhecida. O N é de dois pares por caso. A qualificação de produto e a dispersão entre utilizadores exigem outros denominadores.

A família de código fechou no commit `76296b86`. A primeira nominal fechou em 6P com cinco processos válidos e um arranque interrompido. Os cinco ficam preservados fora dos pares desta tabela. A repetição integral usou `7c08172a` e acrescentou apenas a identificação prospetiva do mapeamento de dados de `/etc/ld.so.cache`. A fixture sem modelo rejeitou dez mutações da VMA. O digest da cache, os campos da VMA e os ELF iniciais e tardios foram verificados. A identidade de código anterior ao lançamento também foi preservada. [Falha e nova janela](nominal-retake.md) · [Série de código e prova de preparação](preflight.md)

## O limite do executor de cálculo

**TRACE_DERIVED_CONDITIONAL.** Os dois processos naturais com pack e trace usaram a mesma trajetória. Cada um avaliou 5+148 posições incrementais com ub32 e produziu 47 IDs. A primeira peça final corresponde à amostra 45. As 48 chamadas, 2 987 callbacks e 2 354 gerações reconciliam por processo. Das gerações antecipadas, 436 tiveram um consumidor obrigatório numa wave posterior da própria camada e tile. A soma usa as durações no relógio de cada produtor e o exterior observado no respetivo cliente. [Protocolo](operator-protocol.md) · [Preços e conservação por fase](bound.json)

| Fronteira | P97 primeiro final (s) | P106 primeiro final (s) | P97 decode de 47 (s) | P106 decode de 47 (s) |
|---|---:|---:|---:|---:|
| Cliente observado com trace | 18,326 | 19,529 | 8,947 | 9,214 |
| Oferecer todas as lacunas após cada wave CPU | 13,207 | 13,812 | 7,089 | 7,062 |
| Oferecer todo o trabalho fora dos callbacks em cada chamada | 12,566 | 13,151 | 6,810 | 6,778 |
| Só READ + três SET, disponíveis ao abrir a sua região | 12,436 | 13,068 | 6,741 | 6,727 |
| Só READ + três SET, todos disponíveis à entrada da chamada | 8,198 | 8,833 | 2,746 | 2,741 |

O crédito à CPU inclui trabalho adjacente entre o fim do callback das camadas 0–24 e o callback ou retorno seguinte. A terceira linha conserva apenas o tempo dos callbacks e o exterior. Para o serviço de pesos, toda a aritmética e a coordenação têm custo zero. Cada grupo de cargas exige pelo menos o maior tempo de um worker e a soma das durações dividida por quatro. Mesmo oferecendo todo o exterior, o piso por região é 12,285 / 12,275 s. A última linha concede o conhecimento dos experts e a disponibilidade dos destinos de toda a chamada. A sua realizabilidade depende de uma agenda e de um mecanismo causal. Os preços individuais de READ e SET podem variar quando mudar a contenção.

**MEDIDO em HTTP local, trace desligado.** No melhor pedido da combinação, o trecho do início da tarefa à alimentação do ID 44 ocupou 17,513 s dos 17,689 s até à primeira peça final. Se o custo exterior a esse trecho desaparecesse, teriam ainda de sair **7,513 s** de dentro dele. No outro processo ON o corte é 8,347 s. O exterior inclui a execução que produz a amostra 45. A mudança do servidor HTTP isolada tem, assim, um ganho máximo de 0,177 / 0,186 s nos dois braços ON mantendo o produtor fixo. [Doze pedidos e cortes por processo](../decision.json)

## Quanto vale conhecer a rota da camada seguinte?

**SIMULATED_ORACLE, NO_GO de uma região nestes dois processos.** Oferecer previsão sempre certa e permitir o READ uma região antes já dá aos quatro workers algumas oportunidades de trabalho. O buffer continua ocupado até ao SET no destino. A tabela inclui o exterior do cliente. Os limites por intervalo e os horários concretos atribuem uma só vez cada serviço, com os mesmos preços do respetivo journal. No decode, o orçamento destes 47 IDs é 7,833 s. [Critérios prospetivos](lookahead.md) · [Resultado e hashes dos horários](lookahead.json)

| Leitura uma região antes | Piso do primeiro final (s) | Horário do primeiro final (s) | Piso de decode (s) | Horário de decode (s) |
|---|---:|---:|---:|---:|
| P97 | 10,285 | 10,462 | 4,829 | 4,921 |
| P106 | 10,921 | 11,106 | 4,819 | 4,909 |

Mesmo com o exterior gratuito, o primeiro final precisaria de 10,135 / 10,128 s. Nos dois horários, 1 030 das 2 354 leituras começaram antes da região de destino, correspondendo a 13 615 776 000 bytes lógicos. O pico foi de três buffers com leituras futuras, dois dos quais chegaram a ficar prontos à espera do destino. A espera acumulada dos workers foi 0,895 / 0,982 s. Identidade futura perfeita, colocação e slots disponíveis dentro da região, cálculo e coordenação gratuitos tornam esta prova otimista. O efeito físico de um predictor tem ainda de pagar erros, contenção e o trabalho do grafo.

**Preço de reabertura.** Com os três SET cobrados, mantendo a libertação na própria região, seria necessário encurtar uniformemente cada READ em pelo menos **21,6251% / 27,4727%** para os pisos admitirem os dois prazos. Com antecipação perfeita de uma região, ainda são **3,0744% / 10,0117%**. Tornar gratuitos todos os SET de CPU e CUDA mantendo a leitura na região deixa 11,416 / 11,961 s. Com essa mesma concessão e uma região de antecipação, os pisos baixam para 9,432 / 9,998771 s. No segundo processo isso deixa no máximo **1,229 ms** para tudo o que o piso idealizou. Os cortes referem-se ao serviço de leitura por geração. Os bytes físicos e o débito efetivamente obtido por outro transporte exigem medição. [Hipótese dos destinos diretos](service-price.md) · [Certificado inteiro ao ppm](service-price.json)

## Duas regiões, destinos CPU e previsão a partir de T1

**TRACE_DERIVED / SIMULATED.** Com duas regiões de antecipação perfeita e quatro buffers, o horário construído cabe em P97. Em P106 até o limite inferior falha em 25,982 ms no primeiro final, com as durações medidas e o exterior observado. O horário efetivamente construído nesse processo excede o prazo em 339,023 ms mesmo oferecendo todo o cálculo. Com uma região de antecipação e SET gratuito apenas na CPU, o piso de P106 fica 394,466 ms acima do prazo. [Pré-registo](frontier.md) · [Resultados, contagens e hashes](frontier.json)

| Concessão, preservando o exterior de cada cliente | P97 primeiro final (s) | P106 primeiro final (s) | P97 decode (s) | P106 decode (s) |
|---|---:|---:|---:|---:|
| READ uma região antes, SET CPU gratuito, SET CUDA pago, piso | 9,810 | 10,394 | 4,542 | 4,496 |
| READ duas regiões antes, ambos os SET pagos, piso | 9,376 | 10,026 | 3,944 | 3,956 |
| Mesma concessão, horário não preemptivo de quatro workers | 9,693 | 10,339 | 4,190 | 4,192 |
| Quarteto por camada escolhido em T1, READ dos acertos desde a entrada da chamada, piso | 12,113 | 12,726 | 6,626 | 6,605 |

O treino leu 87 736 registos autenticados antes de T2 e usou 5 727 reservas. Cada quarteto foi selado antes de ler T2. Só 106 das 2 354 gerações pertenciam aos quartetos, 1 401 235 200 B de payload. Mesmo oferecendo todas as previsões erradas e antecipação ilimitada dentro da chamada para os acertos, o piso falha nos dois processos. Considerar todos os experts com informação futura, a duas regiões, antecipou 1 249 leituras nos dois horários, 16 510 780 800 B lógicos. Dos 2 354 serviços deste pedido, 1 594 correspondem a destinos CPU e 760 a CUDA. O decode natural, incluindo o seu EOG, pagou 14 422 147 200 B de pesos lógicos nas 1 091 gerações de 47 IDs, em média 306,85 MB por ID. O contador de payload não mede tráfego físico do NVMe nem a duração exposta de cada cópia.

## Combinar antecipação e colocação direta

**GO apenas para a fixture.** O mesmo horário de quatro workers com antecipação perfeita de duas regiões **e** entrega praticamente gratuita nas camadas CPU termina em **9,257 / 9,856 s** ao primeiro final e **3,944 / 3,915 s** no decode. O controlo com o mesmo algoritmo e SET CPU pago reproduz inclusive o digest dos eventos do estudo anterior. O limite por intervalos, conservando os SET CUDA completos e pagando cada READ, exige pelo menos 5,5777% de redução uniforme do SET CPU em P106, e zero em P97. Esse desconto apenas faz o piso tocar os prazos. No horário construído, com 1 ns de entrega por geração CPU, o orçamento que sobra para toda a aritmética, predição, contenção e coordenação expostas ao primeiro final é **742,659 / 143,561 ms**. Mesmo com entrega CPU gratuita, a regra dos quatro favoritos de T1 dá pisos de 11,551 / 12,102 s. O resultado abre o teste do local onde a CPU lê os pesos. A parte de conhecer antecipadamente os experts carece de um sinal causal melhor. [Hipóteses e critério conjunto](composition.md) · [Dois horários e cortes certificados](composition.json)

**MEDIDO na CPU do portátil.** O scheduler do GGML C269 existente aceita que as três matrizes MXFP4 de um expert ocupem um registo contíguo alinhado e que cada tensor use o stride desse registo entre experts. A fixture abriu o ficheiro sintético no NVMe interno com O_DIRECT e alinhamento de 4 096 B. Quatro leitores entregaram registos nos slots 0, 13, 27 e 39, com entrega de uma nova geração no slot 13 após o grafo anterior concluir. Os três `MUL_MAT_ID` de dimensão 2 880 × 2 880, quatro ranks e grupos de 1, 20 e 32 posições devolveram **14 653 440 B F32 finitos idênticos** nos três braços. O controlo planar e o controlo com o novo stride fizeram 15 SET de pesos, 66 096 000 B cada. A leitura direta para o slot fez zero SET de pesos. Cada braço pediu os mesmos 66 109 440 B em cinco leituras. O mutante que rodou as três projeções divergiu. O padding adicional do layout é de 2 688 B por slot, 107 520 B por camada de 40 slots. Este teste qualifica o layout nos operadores observados. Os seus dados são sintéticos e a sua duração não mede o ganho do pedido. [Protocolo de operador](slot-layout.md) · [Comparação bitwise, I/O e utilização de recursos](slot-result.json)

A primeira tentativa parou antes da primeira carga do controlo por exigir que `statx` reportasse o alinhamento. A segunda usou o header do leitor C291 que consulta o setor do Btrfs do mesmo inode. A execução fechou em 1,744 s no intervalo observado pelo runner, pico de 272 781 312 B no scope e swap zero. A prova de destinos diretos fez todas as publicações antes da leitura pelo grafo. O horário antecipado conserva a posse do buffer do worker e pressupõe que o destino fica disponível dentro da região. **Combinar os dois resultados fisicamente exige que a geração antiga do slot tenha terminado o seu último consumidor antes do `pread`**, ou expor o novo buffer com custo contabilizado quando isso acontecer. Uma leitura antecipada que ainda dependa de copiar o registo perde parte do crédito. O próximo discriminante é ligar início de READ, último consumidor/pin da vítima, publicação, cancelamento e primeira utilização da nova geração, sem informação de T2 no preditor. Nessa fronteira o controlo usa os mesmos quatro workers, o mesmo stride e as três cópias ativadas. [Interrupção preservada e retoma](slot-retake.md) · [Inventário privado da fixture](slot-archive.json)

**Decisão de investimento.** Conservar o pack e a fusão como componentes medidos. Continuar o trabalho de colocação na extensão do backend atual. Só se justifica um executor dedicado se o Tesy identificar um impedimento concreto na gestão dos destinos e demonstrar tempo suficiente no cliente depois de cobrar a solução. A melhor conversa natural desta composição de pack e fusão ficou a 7,689 s do primeiro final e a 0,643 tok/s do decode pedidos. A escolha do controlo operacional e a qualificação de outros perfis de hardware dependem dos contratos de produto.

## O grafo e a vida do slot no caminho do cliente

**NO_GO para duas regiões de previsão perfeita e destino CPU direto, conservando o custo dos intervalos do grafo observados.** Ao reabrir as 2 987 waves em cada journal, as **853 e 854** leituras CPU começadas antes da respetiva região puderam respeitar a última utilização da vítima. Em 40 reservas CPU a vítima foi usada na mesma região, incluindo 18 sucessões entre cargas novas do mesmo slot. Nenhuma dessas leituras foi adiantada antes do uso anterior no horário testado. Com grafo gratuito, as barreiras por wave e a proteção do parking reproduziram **9,257 / 9,856 s** ao nanossegundo. Este resultado é um horário condicional para os pesos e não estabelece que o target conhece o destino antes do router. [Pré-registo e regra de posse](slot-lifetime.md) · [Horários, pisos e contagens](slot-lifetime.json)

| Dois processos da mesma conversa | Primeiro final P97 / P106 (s) | Decode de 47 IDs P97 / P106 (s) |
|---|---:|---:|
| Piso, intervalos do grafo gratuitos | 8,958 / 9,566 | 3,710 / 3,695 |
| Horário validado, intervalos gratuitos | 9,257 / 9,856 | 3,944 / 3,915 |
| Piso, intervalos do grafo ao preço observado | **11,408 / 12,373** | 4,914 / 5,092 |
| Horário validado, intervalos ao preço observado | 12,259 / 13,317 | 5,157 / 5,331 |

O piso permite sobrepor serviço às lacunas entre callbacks e disponibiliza a vítima assim que estão presentes os pesos dos seus últimos consumidores. O horário construído espera pela fronteira que encerra a wave. Em cada processo contam-se 1 440 slots iniciais, 10 450 procuras, 2 354 READ, 7 062 SET originais e 2 354 publicações, com zero cancelamentos. Em P97 o piso já falha a 50% das durações de grafo originais, e em P106 já falha a 21%. A 49% e a 20%, respetivamente, cabe apenas a condição necessária. Os preços vêm de dois processos do pack com trace ligado e incluem trabalho fora do manager. A hipótese de escalamento uniforme serve para quantificar a diferença. O ganho de fusão medido na conversa tem o seu próprio relógio. As restrições de predição e cópias de uma arquitetura com outro conjunto de faltas exigem avaliação própria.

O primeiro processo encerrou ao verificar a árvore Git. Os destinos exclusivos `outputs/ready-slot-lifetime-20261127-02` e `-03` deram recibos e quatro ficheiros de horário comprimidos idênticos byte a byte. Durações 7,54 / 7,57 s, máximo 188 132 KiB de RSS, zero cálculos de modelo ou GPU. Recibo SHA-256 `b024b4dbcb93690fe17864815a591f7a508b0c2d0e55c45f2af6be9b9bd48739`. [Falha preservada e retoma](slot-lifetime-retake.md)

## Que parte das esperas desaparece com um banco secundário de RAM?

**NO_GO para a seleção causal testada, mesmo com entrega CPU direta e o crédito máximo à fusão.** O replay isolou a contribuição da retenção ao executar cada braço com os mesmos quatro workers, slots primários e capacidade de RAM. Cada coluna mostra o tempo até ao primeiro conteúdo final em P97 / P106, dois processos da mesma conversa nominal. O piso é uma condição necessária. O horário construído respeita a posse dos slots sob os custos assumidos. [Protocolo](slot-bank.md) · [Todos os braços, horários, relógios de decode e selos](slot-bank.json)

| Uso da RAM | Quando uma falta pode iniciar a leitura | Piso com grafo observado (s) | Piso com crédito à fusão (s) | Horário com crédito à fusão (s) |
|---|---|---:|---:|---:|
| Reservada, sem reuso | Entrada da região | 17,084 / 18,210 | 15,868 / 16,887 | 16,440 / 17,500 |
| Reservada, sem reuso | Quatro favoritos de T1 podem começar duas regiões antes | 16,787 / 17,900 | 15,577 / 16,583 | 16,286 / 17,328 |
| Reservada, sem reuso | Previsão perfeita duas regiões antes | 11,408 / 12,373 | 10,753 / 11,604 | 11,301 / 12,222 |
| Retenção por frequência | Entrada da região | 14,753 / 15,917 | 13,537 / 14,594 | 14,034 / 15,115 |
| Retenção por frequência | Quatro favoritos de T1 podem começar duas regiões antes | 14,705 / 15,868 | **13,489 / 14,545** | 14,014 / 15,093 |
| Retenção por frequência | Previsão perfeita duas regiões antes | 9,885 / 10,901 | 9,024 / 9,959 | **10,646 / 11,670** |

A política aprendeu no primeiro turno, começou o segundo com 305 registos secundários e podia ocupar 353 (4 667 326 464 B antes de metadata). A sequência de gerações reproduziu 474 hits CPU e 217 CUDA, retirando **691 das 2 354 leituras** em cada replay. Ficaram 880 no prefill, 763 na parte do decode anterior ao primeiro final e 20 na cauda. A retenção requer 1 367 capturas CPU e 615 CUDA. São 26 200 454 400 B de pesos capturados e 9 134 467 200 B promovidos, antes de qualquer amplificação física. O limite oferece as capturas, a promoção CPU e as previsões desperdiçadas. Cada entrega CUDA continua a cobrar os seus três SET. O crédito integral às 711 lacunas após waves CPU elegíveis vale 1,216 / 1,323 s de trabalho no journal. A fração efetivamente exposta na biblioteca com fusão precisa de medição. No braço que conhece a rota à entrada da região, atingir sequer a condição necessária exige encurtar de forma uniforme o tempo dos READ restantes em **41% / 54%**, ao ponto percentual inteiro. A 40% / 53% o primeiro final ainda excede 10 s.

**INCONCLUSIVE para o horário ótimo com previsão perfeita, retenção e crédito integral à fusão.** Uma leitura tem de caber inteira num worker. Em cada intervalo, a nova prova distribui exatamente pelos quatro workers as doze maiores obrigações, ou todas se houver menos. Um segundo algoritmo confirma os limites das arestas por chamada. O piso do primeiro final sobe para **9,053665138 / 9,992784952 s**, e o do decode de 47 IDs para 4,628532093 / 4,819613299 s. Em P106, qualquer custo adicional inevitavelmente exposto acima de **7,215048 ms** até à primeira peça fecha a combinação nesses preços. A existência de um horário dentro do prazo continua por demonstrar. O horário construído mais rápido desta unidade para este braço dá 10,645585851 / 11,670407779 s. O caso de código e uma segunda trajetória natural não entraram nesta projeção. [Protocolo e critério de saída](slot-packing.md) · [Recibo](slot-packing.json) · [Certificado compacto verificável em CPU](packing-paths.json.gz)

Uma nova arquitetura merece teste se conseguir mudar o preço de servir as faltas críticas ou a informação disponível para as antecipar. Para reabrir a mesma combinação a observação discriminante é um horário causal dentro dos 10 s com preços contemporâneos do caminho crítico, incluindo o serviço entre waves com a fusão ativa, a movimentação do banco, as previsões desperdiçadas e o drain no relógio aplicável. O replay atual exclui as variantes causais da tabela aos preços estudados. A prova inteira confere o limite exclusivamente no braço com informação futura perfeita.

## Proveniência das saídas

Os três protocolos acima foram congelados antes das respetivas execuções. As duas reproduções da composição com banco demoraram 6,12 / 6,10 s e as do certificado inteiro 5,43 / 5,44 s. Em cada par, o conteúdo integral das duas saídas coincidiu byte a byte. Os sete destinos exclusivos incluem a falha inicial de proveniência. O ficheiro comprimido público contém os custos das arestas em nanossegundos e a identificação criptográfica dos dois journals. Os journals e os horários por geração continuam no arquivo privado. A verificação pública abaixo confere a aritmética das arestas. A conferência da extração das obrigações exige os journals privados. [Inventário, commits, árvores, ficheiros e comandos de cada execução](slot-campaigns.json)

O arquivo exclusivo `ready-supplied-wave-20261127-01` contém 538 ficheiros, 593 951 255 B. A reabertura das famílias a partir desse arquivo reproduziu `decision.json` byte a byte. Os replays duplicados do limite do executor duraram 4,06 / 3,99 s, os de uma região 3,96 / 3,98 s, os de preço de READ 1,02 / 1,02 s, o treino 0,47 / 0,42 s e os de duas regiões 4,48 / 4,46 s. O horário, os quatro ficheiros de testemunhas de uma região e os dois de duas regiões conferiram por SHA-256 nas duas reproduções. A composição repetiu em 4,64 / 4,60 s, máximo de 136 972 KiB RSS, com o mesmo SHA-256 `02beb453cbc65d6d481a45c5f7faae51cc39f27dcfc64a5539735c1a6ea0bdc8`. O segundo arquivo `ready-record-slot-20261127-01` contém 26 ficheiros, 190 968 235 B, incluindo a tentativa que falhou. Todos os recibos indicam o commit, a fonte ou o seu protocolo congelado. [Manifesto físico e dos replays](archive.json) · [Manifesto da composição e da fixture](slot-archive.json)

## Reprodução

Na raiz do clone, a conferência do resultado compacto e os testes de conservação usam CPU, sem pesos. `TESY_PFJ_ARCHIVE` aponta à cópia privada `qualification-20261124-nvme-01`, e `TESY_RENEWAL_ARCHIVE` a `ready-renewal-20261127-01`. Para repetir a avaliação nativa a partir das capturas, `TESY_SUPPLIED_PART` aponta à `part-01` do arquivo da unidade física. [Comandos físicos](commands.json) · [Comandos e hashes dos replays](slot-campaigns.json) · [Falha no pré-voo de código](preflight.md) · [Retoma nominal](nominal-retake.md)

```sh
s=research/ready-experts/cpu_wave/supplied
python3 -IB "$s/review.py" --check "$s/decision.json"
python3 -IB "$s/slot_packing.py" --certificate "$s/packing-paths.json.gz" --receipt "$s/slot-packing.json"
python3 -m pytest -q tests/test_supplied_wave.py
out=$(mktemp -d)
python3 -IB "$s/executor_bound.py" --archive "$TESY_PFJ_ARCHIVE" --new-output-dir "$out/bound"
python3 -IB "$s/lookahead.py" --archive "$TESY_PFJ_ARCHIVE" --parent "$out/bound/bound.json" --new-output-dir "$out/one"
python3 -IB "$s/service_price.py" --bound "$out/bound/bound.json" --schedules "$out/one" --new-output-dir "$out/price"
python3 -IB "$s/frontier.py" train --archive "$TESY_PFJ_ARCHIVE" --new-output-dir "$out/plan"
plan_sha=$(sha256sum "$out/plan/plan.json" | cut -d ' ' -f 1)
python3 -IB "$s/frontier.py" score --archive "$TESY_PFJ_ARCHIVE" --lookahead "$out/one/lookahead.json" \
  --bound "$out/bound/bound.json" --price "$out/price/service-price.json" --plan "$out/plan/plan.json" \
  --plan-sha256 "$plan_sha" --new-output-dir "$out/frontier"
python3 -IB "$s/composition.py" --archive "$TESY_PFJ_ARCHIVE" --plan "$out/plan/plan.json" --new-output-dir "$out/composition"
python3 -IB "$s/slot_lifetime.py" --archive "$TESY_PFJ_ARCHIVE" --new-output-dir "$out/slots"
python3 -IB "$s/slot_bank.py" --archive "$TESY_PFJ_ARCHIVE" --renewal "$TESY_RENEWAL_ARCHIVE" \
  --plan "$out/plan/plan.json" --new-output-dir "$out/bank"
python3 -IB "$s/slot_packing.py" --archive "$TESY_PFJ_ARCHIVE" --renewal "$TESY_RENEWAL_ARCHIVE" \
  --new-output-dir "$out/packing"
python3 -IB "$s/review.py" --code "$TESY_SUPPLIED_PART/tesy-wave-supplied-code153-20261127-r02" \
  --nominal "$TESY_SUPPLIED_PART/tesy-wave-supplied-nominal153-20261127-r02" \
  --code-window "$TESY_SUPPLIED_PART/tesy-wave-supplied-c55-code-20261127-r01" \
  --nominal-window "$TESY_SUPPLIED_PART/tesy-wave-supplied-c55-nominal-20261127-r02" \
  --new-output-dir "$out/physical"
```
