# Referências — leitura curta para apresentar à orientadora

Fontes primárias confirmadas. Nenhuma percentagem de outro artigo foi atribuída ao Tesy.

1. **Shazeer, N., Mirhoseini, A., Maziarz, K., Davis, A., Le, Q., Hinton, G. & Dean, J. (2017)**. *Outrageously Large Neural Networks: The Sparsely-Gated Mixture-of-Experts Layer*. ICLR 2017. https://arxiv.org/abs/1701.06538  
   **Porque importa:** conditional computation e routing sparse; fundamento do MoE.

2. **Fedus, W., Zoph, B. & Shazeer, N. (2022)**. *Switch Transformers: Scaling to Trillion Parameter Models with Simple and Efficient Sparsity*. JMLR, 23(120), 1–39. https://www.jmlr.org/papers/v23/21-0998.html  
   **Porque importa:** benefícios e desafios de routing e comunicação em MoE à escala.

3. **Tang, P., Liu, J., Hou, X., Pu, Y., Wang, J., Heng, P.-A., Li, C. & Guo, M. (2024)**. *HOBBIT: A Mixed Precision Expert Offloading System for Fast MoE Inference*. https://arxiv.org/abs/2411.01433  
   **Porque importa:** offloading, prefetch e cache sob limitação de memória. **Diferença importante:** HOBBIT admite caminhos mixed precision de experts que não são a hipótese central de preservação dos pesos Tesy.

4. **Yu, H., Cui, X., Zhang, H., Wang, H. & Wang, H. (2025)**. *fMoE: Fine-Grained Expert Offloading for Large Mixture-of-Experts Serving*. https://arxiv.org/abs/2502.05370  
   **Porque importa:** decisão fina de offloading, caching/prefetch e serving. Experiências em sistema multigpu, não baseline direto do portátil Tesy. **Não confundir** com FastMoE, framework de treino distribuído de MoE.

## Para leitura posterior
- **Leviathan, Y., Kalman, M. & Matias, Y. (2023)**. *Fast Inference from Transformers via Speculative Decoding*. https://arxiv.org/abs/2211.17192. Contrato de verificação; não demonstra que a integração EAGLE3 concreta é rápida.
- *Layered Prefill* (MLSys 2026), relevante para discutir programação de prefill e reutilização, não prova de redução física de NVMe nos pools Tesy: https://proceedings.mlsys.org/paper_files/paper/2026/hash/c0f460c6d63599ea870ba9db63dc96a9-Abstract-Conference.html

## Fronteira da contribuição
**Prior art:** conditional computation, MoE, expert offloading, caching, prefetch, speculative decoding.  
**Tesy — evidência própria:** feasibility de um target 120B de consumo; optimizações internas wave-skip, layout lossless e reuso por tiles em âmbitos distintos, com limites medidos.  
**Por fazer:** comparar com runtimes maduros sob constraints equivalentes, separar efeitos causais, qualificar qualidade/continuidade e delimitar contribuição de tese. `BROAD_NOVELTY_NO_GO / ENGINEERING_AND_MEASUREMENT_GO`.
