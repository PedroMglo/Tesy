# GUIÃO ORAL COMPLETO — TESY / PRIMEIRA REUNIÃO COM DIANA

**Objetivo:** fala para os 10 slides do PowerPoint V3; **12 min 10 s de exposição planeada + ~2 min 50 s de discussão**, ajustáveis ao ritmo. Redação oral em PT-PT, com frases que podes dizer quase literalmente. **Uso privado.**

**Mensagem que não deve perder-se:** há melhorias internas de execução medidas no Tesy (waves, layout lossless e reuso delimitado), mas ainda não está demonstrada superioridade arquitetural global sobre um runtime stock bem configurado. Mais slots significa mais memória, não inovação por si só.

**Como usar:** ler o texto do slide, sem ler o campo «Se perguntar» salvo se necessário. Se estiveres atrasado, encurta o slide 8 e o slide 9; protege os slides 4, 5, 6 e 10.


## Roteiro rápido

| Slide | Tema | Tempo |
|---|---|---:|
| 1 | Apresentação e objetivo | 0:35 |
| 2 | Porque é um problema difícil | 1:05 |
| 3 | O que o Tesy tenta otimizar | 1:15 |
| 4 | Resultado 1 — wave skip | 1:45 |
| 5 | Resultado 2 — layout lossless | 1:30 |
| 6 | Resultado 3 — reutilização entre tiles | 1:45 |
| 7 | O que está demonstrado — e o que não está | 1:10 |
| 8 | Principais entraves e hipóteses rejeitadas | 0:55 |
| 9 | Referências científicas e prior art | 0:50 |
| 10 | Pergunta de tese e pedido à orientadora | 1:20 |

---

## Texto para dizer, slide a slide


### Slide 1 — Apresentação e objetivo (0:35)

**Ao mostrar:** Mostrar o título e o hardware. Não começar já pelos benchmarks.


> Boa tarde, professora Diana. Obrigado por disponibilizar este tempo. Queria apresentar-lhe um projeto de investigação que tenho vindo a desenvolver, chamado Tesy, e perceber se faz sentido transformá-lo na minha tese de mestrado.


> A área é a inferência local de modelos de linguagem de grande dimensão, mais concretamente modelos Mixture-of-Experts, ou MoE, quando a memória disponível é muito inferior ao tamanho do modelo.


> Já tenho protótipos e resultados medidos, tanto positivos como negativos. Hoje não queria defender uma arquitetura fechada: queria mostrar-lhe o problema, o que já aprendi e discutir consigo qual poderá ser uma pergunta de investigação académica sólida.


**Se ela perguntar:** O nome Tesy designa o projeto de investigação; não é um novo modelo de linguagem nem uma arquitetura Transformer treinada de raiz.


### Slide 2 — Porque é um problema difícil (1:05)

**Ao mostrar:** Apontar para Capacidade → Movimentação → Latência útil.


> O caso de estudo que tenho usado é o GPT-OSS 120B, no seu formato MXFP4, num portátil com uma RTX 4060 de 8 GiB de VRAM, 32 GiB de RAM e armazenamento NVMe.


> Um modelo MoE possui vários módulos especializados, chamados experts. Um router escolhe apenas alguns deles para cada posição. É a chamada sparsity de ativação: não é necessário executar todos os experts em cada token.


> Mas há uma diferença entre não executar um expert e não precisar de armazenar os seus pesos. Quando um expert selecionado não está disponível na memória certa, temos de o servir através de RAM, GPU ou armazenamento. Isso acrescenta latência, cópias e sincronizações.


> Por isso, a minha pergunta não é apenas «conseguimos abrir o 120B?». É «quanto custa obter uma resposta útil e onde estão realmente os gargalos?». E separo duas fases: prefill, que processa o prompt, e decode, que gera os tokens seguintes.


**Se ela perguntar:** MoE significa que apenas parte dos experts é ativada por posição. Não significa que o modelo inteiro ocupe 8 GiB.


### Slide 3 — O que o Tesy tenta otimizar (1:15)

**Ao mostrar:** Seguir o diagrama NVMe ↔ RAM/CPU ↔ VRAM/GPU; ler a frase sobre o router original.


> A ideia do Tesy é intervir na forma como os experts são disponibilizados à execução, em vez de modificar a decisão do próprio modelo.


> O router continua a escolher os experts originais; o top-k, isto é, quantos experts são usados por posição, mantém-se; e os pesos do target são os originais.


> O que pode variar é a residência: quais os pesos que estão disponíveis na memória da GPU, quais permanecem em RAM, quando faz sentido carregá-los e quando uma operação pode ser feita na CPU. O NVMe funciona como um nível mais lento do armazenamento. O desenho é conceptual: não estou a afirmar que cada pedido atravessa fisicamente todos estes níveis.


> A dificuldade é encontrar o equilíbrio. Mais cache pode melhorar a latência, mas custa memória; antecipar leituras pode esconder espera, mas também pode criar contenção. Por isso procuro medir os mecanismos e manter o comportamento autoritativo do modelo.


**Se ela perguntar:** Expert residency = quais os experts cujos pesos estão prontos num determinado tier. Prefetch apenas pode preparar movimento; nunca substitui o router.


### Slide 4 — Resultado 1 — wave skip (1:45)

**Ao mostrar:** Apontar para as barras OFF=100% e ON=24,65% / 72,28%.


> Este é um dos resultados que considero mais significativos do ponto de vista da implementação.


> No caminho de execução dos experts, quando os experts pedidos não cabem todos na mesma passagem, o processamento pode ser dividido em waves. Encontrámos trabalho que estava a ser executado para pares de token e expert que não contribuíam naquela wave. O mecanismo de wave skip evita essas operações desnecessárias.


> No ensaio C104, comparei o mecanismo desligado e ligado no mesmo executável e com as mesmas bibliotecas, em dois pares de execuções controladas. O gráfico está normalizado: desligado é 100% da duração; ligado ficou em 24,65% no prefill frio e em 72,28% no prefill incremental.


> Ou seja, neste workload, a duração do prefill diminuiu aproximadamente 75,35% e 27,72%, respetivamente. Isto não aconteceu simplesmente porque aumentei a memória disponível para a cache.


> Há uma ressalva importante: outra comparação entre builds encontrou uma regressão de decode. Portanto, este resultado demonstra uma melhoria interna expressiva naquele contraste, mas ainda não demonstra que o Tesy completo seja superior a outro runtime ou mais rápido em todas as fases.


**Se ela perguntar:** C104: duas comparações emparelhadas no mesmo executável. C100: três pares entre builds, com prefill positivo mas regressão de decode. São experiências distintas e ambas continuam válidas.


### Slide 5 — Resultado 2 — layout lossless (1:30)

**Ao mostrar:** Indicar «Antes / Depois» e os dois ganhos; esclarecer que são reduções de tempo total.


> O segundo resultado é interessante porque não depende de ter mais slots. A questão era se conseguimos entregar os mesmos pesos de forma mais eficiente.


> Em vez de tratar os componentes dos experts apenas na disposição de origem, o protótipo reorganizou o serviço desses componentes de forma mais contígua por expert. Digo lossless porque os bytes e os valores do target foram preservados: não é uma quantização mais agressiva nem uma aproximação do routing.


> Na campanha C293, usando o mesmo perfil numérico e comparações emparelhadas, o custo integrado do trabalho fornecido baixou cerca de 7,47% no caso nominal e 6,05% no caso de código. Em verificações selecionadas, os 33 logits completos coincidiram bit a bit com a referência.


> O ganho foi inferior ao critério interno que tínhamos definido para investir numa integração maior. Mas isso não invalida o resultado: significa que foi uma melhoria medida, ainda insuficiente para a nossa decisão interna de promoção. E atenção: não estou a dizer que a geração completa de uma resposta de código ficou 6% mais rápida neste teste.


**Se ela perguntar:** Bitwise quer dizer igualdade exata dos bytes comparados na amostra testada, não prova de igualdade universal de todos os contextos e métodos de sampling.


### Slide 6 — Resultado 3 — reutilização entre tiles (1:45)

**Ao mostrar:** Explicar em 20 s tile-major vs expert-major; depois apontar ganhos e regressão.


> A terceira linha surgiu de uma hipótese estrutural: se um expert é necessário em vários blocos de posições, será que o conseguimos carregar uma vez e reutilizá-lo antes de o substituir?


> No percurso tile-major, processamos um bloco e avançamos para outro, podendo recarregar experts entre blocos. No protótipo expert-major, começamos por conhecer a união dos experts realmente exigidos e tentamos servir várias referências com a mesma carga, respeitando o routing original.


> A primeira integração mostrou aproximadamente 18,19% menos tempo de prefill num ensaio de trabalho fornecido. Noutra experiência, com geração livre de código, o primeiro conteúdo final apareceu cerca de 8,91% mais cedo. São resultados distintos, não percentagens que se possam somar.


> Depois fizemos uma avaliação causal mais exigente. Num workload nominal apareceu uma regressão de cerca de 10,7% no decode; o desenho experimental alterava também a geometria de atenção e router. Por isso, não posso atribuir todo o ganho apenas a menos recargas, nem apresentar este perfil como uma melhoria geral já validada.


> É precisamente aqui que quero fazer investigação: distinguir ganhos locais reais de melhorias que sobrevivem à inferência completa.


**Se ela perguntar:** Tile é um pequeno bloco de posições. Expert-major não prevê routing futuro: reorganiza referências cujos experts já foram selecionados pelo router autoritativo.


### Slide 7 — O que está demonstrado — e o que não está (1:10)

**Ao mostrar:** Mostrar primeiro «Demonstrado», depois «Ainda por demonstrar».


> Aqui faço uma distinção que considero fundamental.


> O Tesy já demonstrou que este 120B pode ser executado neste portátil em condições concretas e que alterações internas, como as waves e o layout lossless, conseguem reduzir tempos medidos.


> Mas ainda não demonstrei que a arquitetura Tesy, vista como um todo, é superior a um llama.cpp ou Ollama bem configurado sob o mesmo orçamento de memória, o mesmo modelo, o mesmo contexto e requisitos de qualidade equivalentes.


> Também não apresentaria como inovação o simples aumento de 32 para 40 ou 44 slots: mais slots permitem mais pesos residentes, mas usam mais memória. É um trade-off de capacidade, não uma demonstração isolada de melhor eficiência arquitetural.


> Os gates que usámos eram decisões internas para escolher em que investir. Gostava de rever consigo o que devem ser os critérios científicos da tese, sem alterar retroativamente resultados ou insucessos.


**Se ela perguntar:** O perfil utilizável hoje é opt-in, não default geral. M3 permanece parcial e o conjunto de objetivos M4 ainda não foi atingido.


### Slide 8 — Principais entraves e hipóteses rejeitadas (0:55)

**Ao mostrar:** Não detalhar as três famílias por inteiro; escolher um exemplo e resumir as restantes.


> Algumas das experiências mais úteis foram as que não compensaram.


> Por exemplo, na linha de speculative decoding, um verificador idealizado parecia ter margem. Mas quando incluímos um draft EAGLE3 real, as propostas rejeitadas, os replays e todo o overhead, o desenho testado ficou mais lento.


> Também houve mecanismos de prefetch capazes de antecipar parte dos experts, mas a movimentação real podia competir com a procura efetiva. E a compressão lossless reduziu bytes numa amostra, sem poupança suficiente para justificar aquele runtime.


> Isto não prova que estas técnicas nunca funcionem. Mostra antes que, neste hardware e nestes desenhos, temos limites físicos e custos de integração que não podem ser ignorados.


**Se ela perguntar:** Uma previsão de melhoria de I/O não é uma medição de latência; reads pedidos não são necessariamente tráfego físico NVMe.


### Slide 9 — Referências científicas e prior art (0:50)

**Ao mostrar:** Apontar para os quatro artigos sem tentar resumi-los em profundidade.


> Esta investigação não começou do zero. Shazeer e colaboradores introduzem a base moderna do Mixture-of-Experts esparso; Switch Transformers mostra o potencial e os problemas de escalar esta arquitetura.


> Mais próximos do que estou a fazer estão sistemas como HOBBIT, que trabalha offloading de experts em cenários com memória limitada, e fMoE, que estuda mecanismos de offloading fino em serving.


> Há diferenças de hardware, precisão e políticas entre esses trabalhos e o Tesy. Não quero reclamar novidade de offloading, cache ou routing esparso. Quero identificar, consigo, se há uma contribuição mais estreita e defensável. Tenho as referências organizadas e posso partilhá-las.


**Se ela perguntar:** fMoE, aqui, é Fine-Grained Expert Offloading for Large Mixture-of-Experts Serving (2025). É distinto do sistema FastMoE, ligado a treino distribuído.


### Slide 10 — Pergunta de tese e pedido à orientadora (1:20)

**Ao mostrar:** Ler a pergunta da tese e deixar de apresentar. Fazer 2–3 perguntas, não um discurso adicional.


> A pergunta que gostava de propor é esta: quais são os ganhos e os limites reprodutíveis de gerir e servir experts de modelos MoE muito maiores do que a memória rápida disponível, sem alterar o routing ou os pesos do modelo?


> Penso numa tese de sistemas, com um baseline maduro congelado, recursos equivalentes, workloads definidos antes das experiências e métricas que incluam tanto a latência como a qualidade das respostas e os custos de memória e transferência.


> O resultado académico poderá ser um mecanismo estreito que realmente compensa ou uma caracterização rigorosa das condições em que estas estratégias funcionam ou falham. Não quero prometer um speedup universal antes de o medir.


> Gostava, sobretudo, da sua opinião sobre três pontos: se esta pergunta está bem delimitada para um mestrado, que baselines considera obrigatórios e quais destas experiências fazem sentido como núcleo científico da tese. Depois disso, gostava de alinhar consigo o plano de trabalho.


**Se ela perguntar:** Evitar decidir ali que “toda a arquitetura Tesy” é a tese. O objetivo da primeira reunião é escolher a pergunta, o desenho experimental e a fronteira da contribuição.


---

## Perguntas prováveis — respostas curtas


**«Qual é a principal inovação?»**  Ainda não reclamo novidade ampla. Há melhorias internas de execução medidas; a novidade académica tem de ser delimitada por prior art e comparações fortes.


**«Porque não basta aumentar a VRAM?»**  Mais memória ajuda, mas não resolve a pergunta sobre eficiência por byte de residência ou custo de serviço. O teste da arquitetura tem de manter os recursos comparáveis.


**«Wave skip é 75% mais rápido que o stock?»**  Não. C104 comparou OFF/ON do mesmo executável Tesy, para prefill e workload delimitados. Não é comparação contra runtime stock.


**«O que é fMoE?»**  Um sistema publicado de fine-grained expert offloading para MoE serving; serve de antecedente científico. Não é o Tesy, nem o FastMoE de treino.


**«O modelo gera realmente respostas?»**  Sim, há um percurso opt-in e avaliações funcionais selecionadas. Isso não constitui qualificação geral nem demonstra o objetivo M4.


**«Que resultado negativo ensina mais?»**  Que um mecanismo mais rápido isoladamente pode perder performance quando incluímos I/O real, contenda, memória, validação e decode.


**«E se não houver uma arquitetura mais rápida?»**  Uma tese pode ser uma caracterização rigorosa dos limites e dos trade-offs, desde que a pergunta e a metodologia tenham contributo verificável face à literatura.


## O que levar

- PowerPoint V3 ou PDF dos mesmos 10 slides; este guião aberto no portátil ou impresso.
- Resumo académico de uma página para entregar, se fizer sentido.
- Glossário completo do Tesy na pasta documental, apenas para consulta.
- Não abrir raw, patches ou um quadro de campanhas Cxxx na primeira reunião, exceto se a professora pedir evidência específica.


## Proveniência

Valores do material documental do Tesy; não foram feitas medições de modelo nesta preparação. Os tempos de fala são planeados e não cronometrados oralmente. Fontes: 

- `C104 — research/C104-WAVE-TOGGLE-RESULT-20260928.md`

- `C100 — research/C100-SERVER-WAVE-CONFIRM-RESULT-20260928.md`

- `C274 — research/C274-BLOCKS-EXPERT-REUSE-CLOSURE-20261004.md`

- `C282 — research/C282-R2-CAUSAL-QUALIFICATION-CLOSURE-20261005.md`

- `C293 — research/C293-INTEGRATED-EXPERT-STORE-COST-NO-GO-20261006.md`

- `C320 — research/C320-EXACT-EXPERT-SERVICE-ARCHITECTURAL-CLOSURE-20261007.md`