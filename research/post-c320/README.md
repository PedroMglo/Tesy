# Reavaliação do Tesy após C320

**23 de novembro de 2026.** O projeto demonstrou inferência do GPT-OSS-120B acima da RAM no portátil e ganhos de mecanismos específicos. O último controlo operacional publicado é R0 `slots40-persistent`, opt-in. **M3 PARTIAL, M4 NOT_MET.** O último fecho experimental é C320, de 7 de outubro. C321 regista a publicação e o estado para retomar. A branch da tese, de 17 de outubro, acrescenta documentação. A decisão desta revisão é investir primeiro na análise de filas do decode e estudar a possibilidade de reutilização no prefill mantendo a geometria de R0. [Decisão de arquitetura e responsabilidades](../../docs/architecture/0004-servico-exato-de-experts.md) · [Literatura e comparadores](literatura.md) · [Inventário Git](repositorio.md)

## 28 de novembro · o custo de antecipar experts no NVMe interno

No turno nominal, prever pelo ID confirmado antecipou 215 das faltas em 474 emissões, contra nove com popularidade e o mesmo número de emissões. Para combinar esse sinal com as rotas de duas camadas antes, o replay verificou todos os 4 000 002 limiares da regra. Nenhum cumpre o nominal a 4,5 GB/s. No portátil, a combinação selecionada a 8 GB/s gerou 1 874 leituras sem consumidor. As leituras até à primeira peça demoraram 11,714–11,896 s mesmo com todo o passo conhecido à entrada. NO_GO para esta emissão e este transporte. A melhor conversa nominal permanece em 17,689 s e 5,357 tok/s. [Medição e decisão](../ready-experts/verifier_wait/forecast/io/README.md)

## 28 de novembro · o custo físico com os experts residentes

Na mesma conversa do 120B, o percurso serial de decode com os pesos do passo nos slots custou 2,004–2,059 s, e o verificador por blocos 2,110–2,175 s. Os 160 forwards de repetição passaram o controlo numérico e tiveram zero faltas. Mesmo com esses preços, o prefill W original deixa o primeiro final acima de 11 s. A investigação passa a precificar a aquisição causal dos pesos e o prefill em conjunto. O melhor pedido nominal de produto mantém 17,689 s e 5,357 tok/s. M3 PARTIAL e M4 NOT_MET. [Experiência, limites e comandos](../ready-experts/verifier_wait/README.md)

Um serviço que aguarda os READ e SET em cada camada, mesmo com o banco causal de 353 registos, ainda deixaria 11,433–11,770 s até à primeira peça. Para reabrir essa arquitetura é preciso identificar como retirar 1,433–1,770 s do caminho crítico. [Limite da entrega por camada](../ready-experts/verifier_wait/service.md)

## 28 de novembro · proponente 20B e decisão sobre o backend

O GPT-OSS-20B previu 30 de 32 IDs do nominal no primeiro ensaio com dois tokens de avanço e história real do 120B. A CPU do portátil teria de produzir essas propostas em menos tempo do que o medido, mesmo concedendo a verificação do target e a seleção ideal dos blocos. Mantendo os 40 slots primários, o 20B inteiramente residente também excederia o orçamento de memória combinado. **NO_GO para a adoção desta configuração.** O registo fixa a redução de prefill necessária para combinar ambas as vias. [Medição do proponente](../ready-experts/draft20/README.md) · [Combinação com o prefill, correção EOG e decisão por braço](../ready-experts/draft20/joint/README.md)

## 27 de novembro · produto em hardware com diferentes capacidades

Uma arquitetura de execução por expert pronto foi confrontada com os dois pedidos nominais do pack. Com sobreposição ideal e serviço medido, os pisos de primeiro conteúdo final são 10,658 e 11,416 s. O executor e a política causal de residência não atingem os dois alvos nos dois processos. Uma seleção retrospetiva de 353 experts com a mesma RAM reduz esses pisos para 9,118 e 9,864 s, com uma margem mínima de 136 ms. A capacidade de encontrar essa seleção antes da mensagem e realizar a sobreposição continua em aberto. [Arquitetura de produto](../../docs/architecture/0005-execucao-local-por-perfil.md) · [Comparação por braço, código e recibos](../ready-experts/README.md)

## Qualificação de produto em 24 de novembro

M3 PARTIAL e M4 NOT_MET. A reanálise da sessão de 20 turnos localizou uma falha de conteúdo ainda sem referência independente para aquela entrada. O replay C322 fecha o fallback que duplica a leitura. A auditoria atual confirma integralmente o GGUF e documenta as condições de RAM, armazenamento e dependências para retomar no portátil. Na colocação USB escolhida pelo Pedro, o limite de transporte dos 32 passos C294 e a reconstrução dos quatro estados de cache excluem atingir seis só escolhendo outras vítimas em R0. A triagem do MoEStream inclui o cabeçalho real e uma fixture de leitura incompleta. [Decisões, recibos e comandos](../qualification-retake/README.md)

## O que sustenta a decisão

As linhas `MEDIDO` abaixo remetem para medições históricas no target, tal como foram publicadas. Nesta revisão foram lidos fontes, patches, fechos, protocolos e recibos compactos. `REPRODUZIDO_MODEL_FREE` designa os cálculos refeitos nesta revisão com esses recibos. Raw físico, GGUF, binários do portátil, sensores atuais, full logits e geração livre não foram reexecutados. O inventário identifica as linhas examinadas e os limites de cobertura.

| Etapa | Evidência e consequência para a arquitetura |
|---|---|
| Fundação e bring-up 20B | Tracer nativo de top-k, gate de IDs OFF/ON, inventário GGUF e simulação LRU/Belady resolveram perguntas diferentes. A revisão de proveniência retirou admissão a vários resultados de capacidade e crossover. A comparação de um operador ou um oracle offline não autoriza um runtime. `--lazy-mode` no pin histórico não marca os experts GPT-OSS como lazy. [Estado da fundação][base] · [Matriz de baselines][matrix] |
| Residency híbrida e integração vertical | Os ensaios de handoff, reinjection e split-graph demonstraram fronteiras selecionadas. Na integração vertical 20B, o erro relativo máximo nos logits foi 0,00856 para tolerância 0,005 e o timing candidato ficou por executar. A conclusão dita a ordem de trabalho: referência independente antes de juntar kernels ou mudar a granularidade. [Síntese científica S02][s02] |
| Scale lab, C1–C6 | Em C2, o 120B em streaming obteve 3,327 tok/s no ensaio de 20 pedidos e 12/12 num piloto de tarefas, contra 10/12 do stock 20B. Pagou 11,48× o tempo agregado desse piloto. São perguntas de capacidade/qualidade útil entre modelos diferentes. C4–C6 localizaram divergências de shape em Flash Attention CPU/GPU quando se mudou ubatch. [C2][c2] · [C4][c4] · [C6][c6] |
| Sessão e waves, até C104 | C52b sustentou 20 pedidos em 70,46 min com 19 reutilizações de prefixo. C54 foi interrompida antes de poder atribuir o custo quente. Em C104, na mesma build e em dois pares, saltar trabalho redundante nas waves reduziu a duração mediana do prefill frio em **75,350%** e do quente em **27,718%**. O page cache estava em estado operacional não controlado. C100, entre builds, conserva a regressão de decode. [C52b][c52] · [C54][c54] · [C104][c104] · [C100][c100] |
| Capacidade, qualidade e contexto, C127–C154 | A mudança 32→40 slots melhorou o decode quente em **23,173%** no nominal confirmado. Também aumentou a residência. C133 terminou naturalmente os 20 turnos e passou **19/20** critérios de conteúdo. C134b recuperou a chave esperada a 7936 IDs de entrada com 85 IDs de saída. Oportunidade de cache fixa L2 a 3 GiB no C135: apenas 40/1077 cargas de decode na simulação global. [C129][c129] · [C133][c133] · [C134b][c134] · [C135/C136][c136] |
| Residência assimétrica, mmap, native64, espera passiva e slots44 | CPU52/GPU44 estimou ~7,15% e ~7,11% nos dois holdouts C164, abaixo dos 8% congelados. O ensaio começou do estado 44 e acrescentou slots CPU vazios. No caminho `mmap` antigo, o custo removível permaneceu inconclusivo. Native64 teve ganho em prefill de input fixo mas, em C196/C198, só **+3,94%** até primeiro final e **−18,01%** no tempo até SQL validado. C225 fechou a espera passiva. C227/C231 fechou a segunda qualificação slots44 após ambos os braços atingirem o cap na tarefa JSON. [C164][c164] · [C189][c189] · [C198][c198] · [C225][c225] · [C231][c231] |
| Readiness, especulação e reutilização, C232–C282 | C235 rejeitou o overlap apenas da primeira projeção. EAGLE3 integrado B8 perdeu perante autoregressão nas duas classes do screen C258. O executor expert-major obteve ganhos de prefill e em código livre, mas o perfil R2 mudou a forma da atenção/router. No ablation C280, R0→E deu **+13,13% prefill e −10,70% decode** no nominal e **+22,16% e +0,63%** no código. R2 não foi promovido. C281 recuperou o launcher R0 e fechou um ciclo real com dois pedidos. [C235][c235] · [C274][c274] · [C282][c282] · [C281][c281] |
| Política lógica, transporte e antecipação, C283–C321 | C286 falhou o custo da nova política lógica. C293, com pesos originais contíguos, ganhou **7,47% nominal / 6,05% código** no trabalho fornecido 153+32. Ficou abaixo do gate integrado. C309 e C318 pioraram o tempo total. Em C319, Zstd fixo poupou ~4,3–4,5% nos pesos alinhados da amostra e o cenário favorável original ficou em 8,90%, abaixo de 20%. C320 fechou sem sobreviventes para composição. C321 é administrativo. [C293][c293] · [Módulos, thresholds e exceções][modules] · [C320][c320] · [C321][c321] |

O artefacto 120B qualificado no lab tem **63 387 346 208 B**, revisão `238abdd290bb874b90a5da1b4549881b7d05c091` e SHA-256 `582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d`. O controlo selecionado nesta revisão usa a identidade histórica P12, slots40, ub32, contexto 8192, medium e controlo autoregressivo. A ligação do GGUF aos testes vem do lock e dos recibos publicados. Instalação atual no portátil: `DESCONHECIDO`. [Lock do lab][lock] · [Identidades do backend, modelos e bibliotecas][identity]

## Quanto tem de melhorar a conclusão assíncrona

A função `prediction_begin` só abre o serviço especulativo depois do prefill. Para os pares ABBA C318, sejam A as durações de R0, B as do staging aprendido e D a duração do decode de B, incluindo o cleanup contado pelo protocolo. O prefixo de preparação está fora de ambos os tempos totais. A pergunta contrafactual é quanto teria de diminuir apenas D, com prefill e restante trabalho fixos. Para o total, cada par tem ganho `1 − (B_total − x × D) / A_total`. Para o decode troca-se o total pelo tempo de decode respetivo. Com dois pares a mediana é a média dos dois ganhos, cada um normalizado pelo próprio controlo. O cálculo conserva os oito braços e confere as percentagens originais antes de resolver para x. [Cliente original][client] · [Pares e contadores publicados][paired] · [Analisador](analyse.py)

| Redução necessária no próprio decode do candidato | Nominal153 | Code153 |
|---|---:|---:|
| Empatar com R0 na mediana do tempo total | 3,65% | 9,25% |
| Alcançar +8% na mediana do total face a R0 | 19,36% | 27,67% |
| Alcançar +15% na mediana do decode face a R0 | 17,62% | 18,02% |

**Classificação:** aritmética `REPRODUZIDO_MODEL_FREE`, cenário `ESTIMADO` condicionado à mesma redução proporcional nos dois braços candidatos de cada caso. As linhas mostram condições de mediana. No gate global basta um caso qualificado, protegendo o total do outro caso a −5%. Na via de +8% os dois pares têm de ganhar no total. Na via de +15% os dois pares têm de ganhar no decode e a mediana do total tem de ser positiva. O gate de fase tem regras próprias. C318 contou 227–228 esperas no nominal e 278/290 no código, mas cada contador só confirma que um worker chegou a esperar. [Avaliador original][costgate] · [Resultado físico C318][c318]

O analisador também recompõe o cenário C136 e o tamanho das uniões C261 a partir dos 36 conjuntos de IDs. No primeiro, **10,665 s** é o que resta depois de conceder todo o decode do pedido ao primeiro conteúdo final. No segundo, **30 de 36 camadas** ultrapassam 40 experts distintos na fase completa. Como os cinco primeiros tokens só podem selecionar 20 IDs distintos por camada, a própria segunda chamada de 148 tokens também excede 40 em pelo menos **cinco** camadas. Os mínimos demonstráveis são 47/41/45/46/42, sem pressupor qualquer ordem de evicção. Estes cálculos motivam uma hipótese separada de prefill que preserve as formas de R0. [Desenho, limites e decisão](../../docs/architecture/0004-servico-exato-de-experts.md)

## Primeiro trabalho da equipa

A partir da raiz da `main`, o primeiro comando reproduz as tabelas sem modelo nem GPU, inclusive num clone de profundidade 1. Os [13 blobs congelados de C321](source-blobs.json) estão na árvore unificada. O leitor identifica o conteúdo pelo OID Git e preserva a proveniência anterior à consolidação.

```sh
python3 research/post-c320/analyse.py
```

Para a primeira reconstrução das esperas, o único input adicional é a pasta `raw/` de C317, ou uma cópia dos oito ficheiros preservando os quatro subdiretórios relativos. São os pares `events.tsv` e `staging.json` dos braços `{nominal153,code153}-{2,3}-trace`, **13 236 026 bytes** no total. A saída do comando acima já enumera os caminhos, tamanhos e SHA-256 do manifesto congelado. O comando seguinte lê os oito ficheiros em modo só de leitura e rejeita faltas ou diferenças antes de publicar as estatísticas. [Manifesto original][raw]

```sh
python3 research/post-c320/analyse.py --raw-dir "$TESY_C317_RAW"
```

O diagnóstico cruza `call/layer/expert/slot/generation`. A ordem dos eventos no staging distingue a procura que encontrou uma leitura em curso daquela que já encontrou os bytes prontos. Todas as durações vêm do relógio do journal primário. O tempo entre o dequeue e o início da primeira cópia é um envelope que inclui procura e sincronização. A soma em worker-µs e a união em µs de parede são publicadas separadamente. A interseção com uma procura enfileirada que acabou por ser aceite e com o WAIT do router localiza episódios candidatos. Uma entrada obsoleta nunca aceite não dá crédito de trabalho útil. O predicado de aceitação posterior é diagnóstico offline e não pode ser usado pela política de produção.

A reconstrução completa precisa ainda de reconciliar o controlo, a agenda dos quatro workers, contenção e cópias. Uma interseção pequena não exclui efeitos posteriores no caminho crítico. Uma interseção grande também não é um speedup. C317 nominal teve overhead mediano de decode **3,256%** para limite 3%. O caso de código passou o seu gate de observação. C318 foi medido integralmente trace-OFF. Não se subtrai overhead nem se transferem segundos entre C317 e C318. [Qualificação C317][c317] · [Instruções de arquitetura](../../docs/architecture/0004-servico-exato-de-experts.md)

**Estado da execução em novembro.** Aritmética e inventário Git reproduzidos. Caminho do analisador testado com fixtures para workers sobrepostos, duas origens de relógio, fila duplicada/obsoleta, identidade de geração e digest divergente. Os oito raw figuram no manifesto e estão ausentes dos objetos publicados inspecionados. Ocupação real: `NOT_RUN_RAW_REQUIRED`. Tempo poupável, paridade de uma implementação nova e benchmark externo: `DESCONHECIDO / NOT_RUN`. O próximo resultado pode fechar a hipótese antes de qualquer alteração de backend.

[base]: https://github.com/PedroMglo/Tesy/blob/7a7d3dcbd1ff8e594ac57459c3db06306083c3ca/IMPLEMENTATION_STATUS.md
[matrix]: https://github.com/PedroMglo/Tesy/blob/7a7d3dcbd1ff8e594ac57459c3db06306083c3ca/docs/architecture/0002-baseline-matrix.md
[s02]: https://github.com/PedroMglo/Tesy/blob/a1f39c84a777b822208f63686657c30d03a38e67/docs/research-reports/campaigns/S02-development-branch-synthesis/sections/06-results.tex
[c2]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C2-FINAL-20260926.md
[c4]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C4-FINAL-20260927.md
[c6]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C6-FINAL-20260927.md
[c52]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C52B-ASSISTANT-HISTORY-SUSTAINED-RESULT-20260928.md
[c54]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C54-WARM-PREFIX-PHASE-INTERRUPTION-20260928.md
[c104]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C104-WAVE-TOGGLE-RESULT-20260928.md
[c100]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C100-SERVER-WAVE-CONFIRM-RESULT-20260928.md
[c129]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C129-SLOTS40-CONFIRM-RESULT-20260929.md
[c133]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C133-DIVERSE-ACTIVE-SESSION-RESULT-20260929.md
[c134]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C134B-SLOTS40-8K-BOUNDARY-RESULT-20260929.md
[c136]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C135-C136-SLOTS40-RESIDUAL-DECODE-20260929.md
[c164]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C164-REPLAY-AND-POLICY-DECISION-20260930.md
[c189]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C189-C143-REAL-PATH-AND-EPOCH-CLOSURE-20260930.md
[c198]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C198-NATIVE64-NATURAL-CLOSURE-20260930.md
[c225]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C225-POST-C209-PASSIVE-WAIT-CLOSURE-20261001.md
[c231]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C231-POST-C225-SLOTS44-CLOSURE-20261001.md
[c235]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C235-READINESS-FEASIBILITY-CLOSURE-20261001.md
[c274]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C274-BLOCKS-EXPERT-REUSE-CLOSURE-20261004.md
[c282]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C282-R2-CAUSAL-QUALIFICATION-CLOSURE-20261005.md
[c281]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C281-PERSISTENT-R0-RESTORATION-RESULT-20261005.md
[c293]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C293-INTEGRATED-EXPERT-STORE-COST-NO-GO-20261006.md
[c320]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C320-EXACT-EXPERT-SERVICE-ARCHITECTURAL-CLOSURE-20261007.md
[c321]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C321-PUBLICATION-SHUTDOWN-HANDOFF-20261007.md
[c318]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C318-LEARNED-STAGING-COST-NO-GO-20261007.md
[c317]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C317-LEARNED-OBSERVER-RESULT-20261007.md
[modules]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/results/c320-exact-expert-service-closure-20261007/modules.json
[lock]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/models.lock.json
[identity]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/results/c320-exact-expert-service-closure-20261007/identity-index.json
[paired]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/results/c318-learned-staging-contemporary-product-cost-20261007/paired-cost-analysis.json
[costgate]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/tools/expert_staging_product_cost_gate.py
[client]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/tools/expert_learned_staging.cpp
[raw]: https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/results/c317-learned-staging-observer-qualification-20261007/raw-manifest.json
