# Perguntas difíceis — treino para os 3 minutos de discussão

**Uso privado:** não entregar este ficheiro como apresentação. As respostas resumem os resultados já documentados e não substituem as campanhas originais.

| Pergunta que pode surgir | Resposta curta e defensável |
|---|---|
| **O que foi efetivamente inovado?** | Melhorámos a execução interna de waves e o serviço dos bytes originais dos experts. Isso é engenharia própria, **não** demonstra novidade científica ampla nem liderança face a outros runtimes. |
| **75% melhor em relação a quê?** | Em C104, wave-skip ON vs OFF **no mesmo executável C75**, dois pares do workload estudado. Não é um benchmark vs Ollama nem llama.cpp stock. C100 tinha regressão de decode cross-build e permanece válido. |
| **O que acontece ao aumentar de 40 para 44 slots?** | Usa mais memória; é um trade-off capacidade/latência. Pode também alterar a geometria das waves. Não é evidência de melhoria arquitetural de eficiência a recursos iguais. |
| **O layout lossless C293 altera o modelo?** | Não altera bytes de pesos, router/top-k nem o R0 no contraste. No âmbito verificado, 33 logits selecionados ficaram bitwise iguais. Isso não prova equivalência geral para todos os contextos e modos de sampling. |
| **Reuso entre tiles provou um ganho?** | Mediu-se −18,19% no prefill fornecido e −8,91% em first-final de código livre, mas C282 observou regressão relevante no decode nominal. C271/C273 e C282 não podem ser misturados nem usados para reclamar ganho geral. |
| **Porque 120B em 8 GiB?** | É um target deliberadamente desafiador, onde residência/serviço de experts se tornam problemas físicos mensuráveis. Não assumo que será a solução mais competitiva de todas as aplicações. |
| **O Tesy é mais rápido que Ollama?** | Não há ainda comparação científica end-to-end suficiente com mesmo hardware, revisão, tokenizer, quantização, contexto, memória, qualidade e serviço. |
| **Quantização adicional ajudaria?** | Pode baixar memória, mas seria uma nova intervenção com trade-off de precisão. O estudo de gestão de experts mantém o GPT-OSS120B MXFP4 original. |
| **Como controlas “exactness”?** | Separo pesos/routing preservados, equivalência bitwise/numerical, identidade greedy e preservação de distribuição. Regressões cross-shape e referências parciais não se tornam garantias universais. |
| **Porque falharam propostas com boa estimativa?** | O custo integrado pode incluir I/O, cópias, contenda, dequantização, proposta/rejeição e overhead; melhorias de microbenchmark ou estimativas não garantem menor tempo para resposta final. |
| **O que seria a hipótese da tese?** | Uma hipótese falsificável sobre onde residence/serviço exato dos experts traz melhoria reprodutível sob budgets fixos, comparando com backend stock e executando workloads/quality equivalentes. |
| **E se nenhuma otimização ganhar globalmente?** | O trabalho pode caracterizar limites físicos e condições em que certos mecanismos compensam, desde que haja desenho experimental controlado e contribuição estreita perante prior art. |

## O que a professora deve decidir contigo

1. Qual é a **pergunta falsificável** suficientemente curta para um mestrado?
2. Quais os **baselines stock** indispensáveis e que workload seria considerado representativo?
3. Quais as métricas primárias: tempo até resultado válido, prefill, decode, residência/I/O e qualidade?
4. Que resultados existentes devem ser **replicados sem enviesamento** e que hipóteses devem ser excluídas?

## Limites de divulgação na primeira reunião

Mostrar o modelo conceptual, o ambiente, os três resultados com âmbito, obstáculos e referências. Guardar para reunião técnica posterior os patches, mecanismos internos de prefetch/eviction, raw, manifests, identidade de todas as campanhas e trade-offs detalhados.

**Estado documentado:** M3 PARTIAL; M4 NOT_MET; perfil `slots40-persistent` opt-in. Os gates eram decisões de engenharia e podem ser redefinidos prospetivamente, sem reclassificar experiências passadas.

**Fonte:** C100/C104, C274/C282, C293/C320 na branch de investigação em `623a5b97b6e14a39bc671f6d81e7a993a3efe7cb`. Nenhuma nova execução do modelo nesta preparação.
