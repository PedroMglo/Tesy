# Guião de fala — primeira reunião com Diana

**Tempo-alvo: 11–12 minutos de exposição, 3–4 minutos de discussão.** Os slides têm speaker notes. Não é necessário mostrar código, branches, patchsets ou campanhas individuais à orientadora.

## Slide 1 — Enquadramento (0:40)
> Tenho vindo a desenvolver o Tesy, um projeto sobre inferência local de modelos *Mixture-of-Experts* (MoE) que são muito maiores que a memória rápida disponível. Quero perceber se é possível melhorar a execução e que limites são impostos pelo hardware. Gostava de discutir consigo se isto pode ser uma tese de mestrado bem delimitada.

## Slide 2 — Porque é difícil (1:00)
> O caso de estudo é um GPT-OSS 120B MXFP4 num portátil com RTX 4060 de 8 GiB, 32 GiB de RAM e NVMe. Num MoE não se ativam todos os experts para cada token. Isso permite só ter parte residente em GPU, mas exige movimentação e gestão cuidadosa dos pesos. O custo não é só capacidade: é transferência, sincronização e latência.

Se pedirem: *prefill* processa o prompt; *decode* produz os tokens seguintes. É preciso medir ambos, não apenas tok/s.

## Slide 3 — Ideia do Tesy (1:10)
> O router do modelo continua a selecionar os experts reais, com os pesos e top-k originais. O que procuro mudar é a forma como os pesos são entregues à computação: memória, cache, ordem de carregamento e organização dos blocos de trabalho. Não altero o routing para obter um resultado mais rápido ou mais conveniente.

O esquema NVMe↔RAM↔VRAM é conceptual. Não afirmar que todas as cargas atravessam fisicamente cada nível, nem que leituras solicitadas equivalem a tráfego físico.

## Slide 4 — Principal ganho: waves (1:55)
> O primeiro resultado que considero realmente relevante para a arquitetura é evitar computação redundante no processamento em waves. No C104 comparei, no mesmo executável C75, a opção desativada e ativada. Naquele workload, o prefill frio demorou aproximadamente 75,35% menos tempo, e o prefill incremental demorou 27,72% menos tempo. O ponto importante é que isto não foi conseguido simplesmente reservando mais slots de memória.

Explica o gráfico: OFF=100% de duração, ON=24,65% no frio e 72,28% no warm. **Limite:** foram dois pares do mesmo workload; outra comparação entre builds (C100) revelou regressão de decode. É ganho interno, não prova de superioridade perante um outro backend.

## Slide 5 — Segundo ganho: layout lossless (1:25)
> Testei também reorganizar o serviço dos componentes de cada expert mantendo os bytes originais do modelo e o mesmo routing. Em trabalho fornecido, o caminho integrado melhorou cerca de 7,47% no caso nominal e 6,05% no de código. Todos os 33 logits completos da referência selecionada permaneceram bitwise iguais. Portanto há evidência de que a organização dos dados interessa mesmo sem mudar os pesos.

**Limite:** não é resposta livre de ponta a ponta e não passou o limiar interno de investimento. A melhoria observada continua válida no âmbito do ensaio.

## Slide 6 — Terceiro ganho e contraexemplo: reuso entre tiles (1:35)
> Outro ensaio investigou se carregar um expert uma vez e servi-lo em vários tiles pode evitar recargas. O protótipo melhorou cerca de 18,19% o prefill no trabalho fornecido e 8,91% o primeiro conteúdo final numa tarefa livre de código. Mas a qualificação posterior encontrou regressão de decode no caso nominal, cerca de 10,7%, e o perfil não foi adotado como solução geral.

Importante: o protótipo R2 alterou também o shape de atenção/router, pelo que não se pode atribuir toda a diferença a menos recargas.

## Slide 7 — O que estes números **não** provam (1:00)
> Há ganhos técnicos internos bem documentados. Ainda não existe uma comparação justa, completa e reproduzível que demonstre que a arquitetura Tesy no conjunto supera um llama.cpp ou Ollama bem configurado no mesmo hardware e requisitos. Além disso, permitir mais slots usa mais memória: isso é um compromisso de capacidade, não uma contribuição arquitetural isolada.

> Os critérios internos de promoção foram uma disciplina de engenharia. Para uma tese, preferia revê-los consigo e escolher métricas e baselines científicos adequados — sem alterar as medições anteriores.

## Slide 8 — Entraves e resultados negativos (0:50)
> Alguns mecanismos tinham ganhos teóricos ou isolados, mas perderam vantagens na integração: overlap, EAGLE3 com draft real, antecipação/prefetch e compressão lossless. Isto ajudou a perceber o que não compensa neste hardware e no desenho testado. Os resultados negativos fazem parte da contribuição experimental.

Não falar de todas as campanhas; um exemplo basta se faltar tempo.

## Slide 9 — Referências (0:40)
> A investigação parte de trabalhos existentes: Shazeer e Switch Transformers para MoE; HOBBIT e fMoE para offloading e caching de experts. Não assumo novidade geral em qualquer destas ideias. O desafio é delimitar uma contribuição específica que sobreviva ao confronto com estes antecedentes.

`fMoE` de Yu et al. (2025) é sistema de offloading de experts para serving; não confundir com `FastMoE` de treino distribuído.

## Slide 10 — Pergunta e discussão (1:10 + 3–4 min)
> A hipótese de tese seria estudar os limites e ganhos reais da gestão exata de experts em inferência MoE *out-of-core*, num envelope de hardware de consumo: medições físicas, comparação com baseline maduro e validação de correctness. A contribuição poderá ser um mecanismo estreito ou, se a física o impuser, um conjunto rigoroso de limites e trade-offs.

Perguntas à orientadora:
1. Como delimitaria a pergunta para um mestrado?
2. Que baselines e métricas exigiria para defender o trabalho?
3. Que subconjunto das experiências vale a pena reproduzir academicamente?

## Respostas curtas para perguntas prováveis

**“O que há de original?”** — Não há ainda prova de novidade ampla. O contributo académico candidato é a análise/otimização estreita do serviço exato de experts no envelope CPU/GPU/NVMe, sujeita a revisão bibliográfica e baselines.

**“Porque não quantizar mais?”** — O target já está no seu formato MXFP4 original. Quantização adicional seria uma intervenção diferente, com trade-off de precisão; aqui pretendo manter os pesos e routing autoritativos.

**“E a melhoria 32→44 slots?”** — Aumenta residência usando mais memória e pode mudar a geometria de execução. Não é a evidência de inovação que quero destacar.

**“É mais rápido que o Ollama?”** — Há observações exploratórias, mas não uma comparação científica suficientemente controlada para reclamar vitória global. Essa comparação é parte do trabalho por fazer.

**“Têm uma solução utilizável?”** — Existe um perfil opt-in (`slots40-persistent`) e protótipos, mas ainda não cumprimos os objetivos conjuntivos M4 nem qualificação geral.

**“Porque tantos testes negativos?”** — Porque poupança de bytes ou latência num microbenchmark não é necessariamente melhoria útil quando toda a inferência, CPU/GPU/NVMe e correção entram na conta.

## Linguagem rigorosa
Preferir `MEDIDO no workload X`, `qualificado neste perfil`, `não promovido`, `controlo comparável`; evitar `provei eficiência global`, `solução revolucionária`, `novo estado da arte`, `melhor que todos os runtimes`.

Em 15 minutos, a conversa deve terminar com um **problema de tese co-definido**, não com uma defesa exaustiva do projeto.
