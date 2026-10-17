# Guião — primeira reunião com a orientadora

Duração alvo: **10–15 minutos** antes de abrir discussão.

## 1. Abertura — 30–45 s

> Tenho vindo a desenvolver o Tesy como projeto de investigação em inferência local de LLMs grandes. O problema que me interessa não é simplesmente conseguir abrir um modelo grande, mas perceber até onde conseguimos levar um MoE que excede claramente a VRAM disponível, mantendo o routing real do modelo e medindo corretamente os custos de memória, transferência e latência.

Não começar por números ou implementação. Primeiro tornar o problema claro.

## 2. Problema e motivação — 1–2 min

> O meu target é um portátil com RTX 4060 de 8 GiB, 32 GiB de RAM e NVMe. O modelo principal é o GPT-OSS 120B MXFP4. Como é MoE, só uma parte dos experts é usada em cada passo. Isso cria a oportunidade de não manter todos os experts na GPU, mas também cria o problema de os movimentar rapidamente entre tiers de memória.

Explicar três custos:

- capacidade: o modelo é muito maior que a VRAM;
- movimentação: um miss pode obrigar a trazer pesos de memória mais lenta;
- latência: prefill e decode não reagem da mesma forma às mesmas decisões.

## 3. O que o Tesy faz — 1–2 min

> A ideia base é manter apenas uma parte dos experts residente e carregar os restantes à medida que o routing autoritativo os pede. O que tento otimizar é a forma de servir os pesos, não a decisão do modelo. Não reduzo top-k, não substituo experts e não altero o routing para fabricar performance.

Termos que podes usar se ela quiser detalhe: `expert residency`, `expert streaming`, `heterogeneous CPU/GPU execution`, `prefetch`, `multi-tier storage`, `prefill` e `decode`.

## 4. O que já consegui — 2–3 min

Mostrar apenas três evidências.

### A. Aumentar residência trouxe ganho real

No workload nominal congelado, passar de 32 para 40 slots de experts por layer reduziu a duração de decode em **23,17%** e o first-final em **18,01%**. Isto foi confirmado em três pares novos; não é apenas um microbenchmark.

### B. Ainda existia headroom de residência

Passar de 40 para 44 slots trouxe mais **11,75%** de redução de decode naquele workload, chegando a **5,236 tok/s**. Mas o first-final continuava em ~19,3 s e o objetivo histórico de 6 tok/s / 10 s não foi atingido.

### C. Reutilização de experts mostrou potencial, mas não foi promovida

Um protótipo posterior conseguiu **18,19%** de melhoria de prefill em trabalho fornecido e **8,91%** de melhoria de first-final numa tarefa de código. A qualificação causal posterior revelou regressão de decode no caso nominal, por isso o perfil não foi promovido. Isto é importante mostrar: o Tesy preserva resultados positivos sem esconder os contraexemplos.

## 5. Entraves que já identifiquei — 2 min

> O maior desafio deixou de ser “o modelo cabe ou não cabe”. É conseguir que a movimentação de experts não domine a execução e provar que uma otimização local continua a ajudar quando é integrada no Transformer completo.

Exemplos curtos:

- overlap mínimo entre carregamento e compute não trouxe margem suficiente;
- EAGLE3/speculative parecia promissor num cenário idealizado, mas o head real ficou mais lento;
- prefetch aprendido conseguiu prever parte dos experts, mas os reads antecipados reais criaram custo/contenda e não melhoraram a latência;
- compressão lossless reduziu alguns bytes, mas o envelope medido não justificou construir um runtime comprimido.

Frase útil:

> Tenho tentado matar hipóteses cedo. Para mim um NO_GO bem medido é melhor do que uma otimização que só parece boa num microbenchmark.

## 6. Como proponho enquadrar a tese — 2 min

> A pergunta que quero transformar em tese é: até que ponto routing sparsity, residência dinâmica e execução heterogénea conseguem aumentar a capacidade e reduzir a latência de LLMs MoE quando o modelo excede a memória rápida disponível, sem alterar o routing autoritativo?

Quatro eixos:

1. **Medição:** separar prefill/decode, tiers de memória, hits/misses e recursos.
2. **Arquitetura:** intervir na menor fronteira possível de serviço dos experts.
3. **Exactness:** correctness antes de performance; não trocar qualidade por um PASS conveniente.
4. **Limites:** documentar também quando um desenho não compensa.

## 7. O que pedir à professora — 1–2 min

Perguntas diretas:

- Esta pergunta de investigação está suficientemente delimitada para uma tese de mestrado?
- Que baselines e critérios de qualidade considera indispensáveis?
- Faz sentido tratar a execução out-of-core exata de MoE como núcleo, em vez de tentar apresentar um runtime completo como contribuição?
- Que resultados já obtidos devem entrar como evidência principal e quais devem ficar apenas como exploração?

## Respostas curtas para perguntas prováveis

### “Qual é a novidade?”

> Ainda não estou a assumir novidade ampla. Expert offloading, caching e prefetch têm bastante prior art. O que estou a tentar perceber é se emerge uma contribuição estreita e defensável no regime de inferência exata de um MoE muito maior que a memória rápida disponível em hardware de consumo.

### “Porque não usar apenas quantização?”

> O modelo já está num formato MXFP4. A quantização reduz capacidade/movimentação, mas não elimina o problema de residência e transferência quando o target continua muito maior que a VRAM.

### “Porque não meter tudo em RAM?”

> Mesmo que uma configuração caiba em RAM, continua a existir o custo RAM→GPU e, para modelos ainda maiores, o objetivo é estudar também envelopes em que a RAM deixa de ser suficiente.

### “Porque não usar apenas CPU?”

> Porque o problema é precisamente encontrar o ponto económico entre compute CPU, GPU e custo de movimentação. O Tesy mede esses regimes em vez de assumir que um tier é sempre melhor.

### “Já tens produto?”

> Tenho um caminho opt-in utilizável e vários protótipos experimentais. M3 continua parcial e M4 não está atingido; não apresentaria o trabalho como produto terminado.

## Linguagem a evitar

Não dizer “provei”, “é mais rápido em geral”, “novo estado da arte”, “resolvi 120B em 8 GB” ou “mantém sempre a mesma qualidade”. Preferir “medi”, “no âmbito testado”, “resultado confirmado neste workload”, “perfil experimental” e “ainda por qualificar”.