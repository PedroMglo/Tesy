# 1.0.1

Revisão material de prior art: inclusão de APEX, Cache-Aware Joint Router Adaptation e estudo consumer/edge; claims ligadas aos mecanismos e limites de exactness/escala. Nova auditoria e PDF CI pendentes.

# 1.0.0

Reaberto como DRAFT em 2026-09-30, antes da primeira publicação, para ampliar e corrigir o mapa de prior art. A revisão:
- usa versões archival verificadas para Shazeer et al. (ICLR'17), LLM in a Flash (ACL'24) e SiDA (MLSys'24);
- acrescenta PreScope, ExpertFlow (DAC'26), FineMoE (EuroSys'26), DALI e pre-attention expert prediction;
- torna explícito que local-PC offload, dynamic CPU/GPU assignment, cache replacement e predictive prefetch já têm prior art direto;
- mantém a separação entre overlap de mecanismo e equivalência do contrato exacto Tesy.

O preview anterior tornou-se stale com esta alteração. Nova compilação e revisão visual são obrigatórias antes de restaurar REVIEWED.

Reaberto novamente em 2026-09-30 para incluir três fontes primárias recentes, todas dentro do corte declarado: APEX (prefetch antes da atenção e dois contratos de execução), Cache-Aware Joint Router Adaptation (adaptação do backbone/cache router no pós-treino) e o estudo empírico de MoE em hardware consumer/edge. As citações foram ligadas às claims de prior art e exactness, e o âmbito limitado do benchmark foi explícito. O PDF CI anterior não corresponde a estes inputs; hash e auditoria editorial têm de ser renovados após a revisão visual do novo artifact CI.

# 0.1.0

Primeira edição DRAFT com evidência interna congelada e bibliografia externa verificada.
