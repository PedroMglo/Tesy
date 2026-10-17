# Tesy — resumo académico para uma primeira reunião

**Tema:** inferência local de modelos Mixture-of-Experts (MoE) muito maiores do que a VRAM disponível, preservando o routing/top-k e os pesos originais do modelo.

**Caso de estudo:** GPT-OSS120B MXFP4 GGUF; portátil Linux, Ryzen AI 9 HX 370, RTX 4060 Laptop com 8 GiB VRAM, 32 GiB RAM e NVMe.

## Problema
O routing de um MoE ativa apenas uma parte dos experts por posição, mas o armazenamento e a movimentação dos pesos têm custos distintos em NVMe, RAM, PCIe e VRAM. O desafio é equilibrar capacidade, latência de prefill/decode e correctness.

## Evidências experimentais selecionadas

| Alteração interna | Resultado no âmbito descrito | Limite da conclusão |
|---|---|---|
| Wave skip C104 | −75,35% no prefill frio e −27,72% no prefill incremental, mesmo executável ON/OFF | Dois pares, um workload; não estabelece vantagem sobre outro runtime. |
| Layout lossless C293 | −7,47% no custo integrado nominal; −6,05% no caso código | Mesmo routing/bytes/slots; trabalho fornecido, não geração livre de resposta. |
| Reuso entre tiles C274 | −18,19% prefill fornecido e −8,91% first-final código em ensaios distintos | Perfil não generalizado: C282 encontrou regressão de decode nominal. |

Mais slots/residência utilizam mais memória: são trade-offs importantes, **não** prova isolada de inovação arquitetural. Os resultados são internos ao Tesy e **não demonstram superioridade global** face a um llama.cpp ou Ollama stock bem configurado.

## Pergunta de investigação proposta
**Quais os ganhos e os limites reprodutíveis de gerir e servir, sem aproximação do routing, experts MoE em inferência out-of-core sob hardware de consumo?**

Metodologia a negociar: baselines maduros, budgets iguais, medição de latência útil por fase, recursos por tier, correção/qualidade e custos end-to-end; hipóteses de ganho e limites falsificáveis.

## Referências essenciais
Shazeer et al. (2017), [Sparsely-Gated Mixture-of-Experts](https://arxiv.org/abs/1701.06538); Fedus, Zoph & Shazeer (2022), [Switch Transformers](https://www.jmlr.org/papers/v23/21-0998.html); Tang et al. (2024), [HOBBIT](https://arxiv.org/abs/2411.01433); Yu et al. (2025), [fMoE](https://arxiv.org/abs/2502.05370).

O Tesy **não reivindica novidade ampla**. Pretende investigar uma contribuição estreita ou um estudo experimental sólido dos trade-offs.

*Preparado para discussão inicial em 17/10/2026; a apresentação e a bibliografia são deliberadamente seletivas.*
