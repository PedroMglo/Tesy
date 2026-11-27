# Quanto ganharia o utilizador com outro backend?

**NO_GO para uma reescrita do executor de cálculo como solução para o primeiro conteúdo final neste portátil.** Com o serviço atual de pesos, até tornar gratuitos CPU e GPU deixa o cliente acima de 10 s nos dois traces. O primeiro alvo continua o GPT-OSS-120B MXFP4 original com histórico e contexto 8192. R0 `slots40-persistent` é o controlo operacional, M3 PARTIAL e M4 NOT_MET. A decisão sobre arquiteturas que mudam a disponibilidade dos pesos tem um teste separado abaixo. [Contrato do perfil](../../../../docs/architecture/0005-execucao-local-por-perfil.md)

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
