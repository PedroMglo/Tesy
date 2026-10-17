# Referências científicas — seleção curta

A primeira reunião não precisa de uma revisão bibliográfica completa. Estas referências são suficientes para mostrar que o Tesy está inserido numa linha de investigação existente e que a contribuição terá de ser delimitada.

## Fundamentos de Mixture-of-Experts

**Shazeer, N.; Mirhoseini, A.; Maziarz, K.; Davis, A.; Le, Q.; Hinton, G.; Dean, J. (2017). _Outrageously Large Neural Networks: The Sparsely-Gated Mixture-of-Experts Layer_.**

Introduz uma formulação moderna de conditional computation com routing sparse e grandes conjuntos de experts. É uma referência fundamental para explicar porque um MoE pode ter muitos parâmetros sem ativar todos em cada exemplo.

- arXiv: https://arxiv.org/abs/1701.06538

**Fedus, W.; Zoph, B.; Shazeer, N. (2022). _Switch Transformers: Scaling to Trillion Parameter Models with Simple and Efficient Sparsity_. Journal of Machine Learning Research, 23(120).**

Mostra a escala que architectures MoE podem atingir e discute custos de routing, comunicação e eficiência.

- JMLR: https://www.jmlr.org/papers/v23/21-0998.html

## Inferência MoE com memória limitada

**Tang, P. et al. (2024). _HOBBIT: A Mixed Precision Expert Offloading System for Fast MoE Inference_.**

Explora expert offloading, prefetching e caching em dispositivos edge. É diretamente relevante como prior art para a família de problemas de movimentação/residência, embora use decisões de mixed precision que o Tesy não assume como autoridade do target.

- arXiv: https://arxiv.org/abs/2411.01433

**Yu, H.; Cui, X.; Zhang, H.; Wang, H.; Wang, H. (2025). _fMoE: Fine-Grained Expert Offloading for Large Mixture-of-Experts Serving_.**

Explora offloading fino e padrões de seleção de experts para orientar caching/prefetch. O envelope de hardware e serving é diferente do Tesy, por isso os resultados publicados não são transferidos como previsão.

- arXiv: https://arxiv.org/abs/2502.05370

## Referências para aprofundar depois da primeira reunião

- Leviathan, Y.; Kalman, M.; Matias, Y. — speculative decoding; útil para explicar a linha EAGLE/speculative, mas não precisa de entrar na apresentação inicial.
- Layered prefill / scheduling MoE — relevante para reutilização de experts entre tiles e reorganização da unidade de execução.
- OD-MoE — on-demand expert loading em edge distribuído; interessante como contraste de arquitetura, não como baseline direto do portátil Tesy.

## Claim boundary

Nenhuma destas referências é usada para reclamar novidade ampla. Expert offloading, caching, prefetch, MoE routing e speculative decoding já têm prior art forte. O Tesy deve procurar uma contribuição estreita que sobreviva a baselines e medição no seu envelope específico.