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

## Reprodução

Na raiz do clone, a conferência do resultado compacto e os testes de conservação usam CPU, sem pesos. Para reabrir os journals do portátil, `TESY_PFJ_ARCHIVE` aponta à cópia privada `qualification-20261124-nvme-01`. Para repetir a avaliação nativa a partir das capturas, `TESY_SUPPLIED_PART` aponta à `part-01` do arquivo desta unidade. Ficheiros e destinos dos lançamentos físicos constam do registo de comandos. [Comandos originais](commands.json) · [Falha no pré-voo de código](preflight.md) · [Retoma nominal](nominal-retake.md)

```sh
s=research/ready-experts/cpu_wave/supplied
python3 -IB "$s/review.py" --check "$s/decision.json"
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
python3 -IB "$s/review.py" --code "$TESY_SUPPLIED_PART/tesy-wave-supplied-code153-20261127-r02" \
  --nominal "$TESY_SUPPLIED_PART/tesy-wave-supplied-nominal153-20261127-r02" \
  --code-window "$TESY_SUPPLIED_PART/tesy-wave-supplied-c55-code-20261127-r01" \
  --nominal-window "$TESY_SUPPLIED_PART/tesy-wave-supplied-c55-nominal-20261127-r02" \
  --new-output-dir "$out/physical"
```
