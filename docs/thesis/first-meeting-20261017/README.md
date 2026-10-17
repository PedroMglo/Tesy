# Tesy — primeira reunião de orientação

Material deliberadamente curto para a primeira reunião com a orientadora. O objetivo é explicar o problema, mostrar evidência suficiente de que existe trabalho experimental real e discutir o enquadramento da tese **sem expor todo o histórico, patches, protocolos, raw ou desenhos experimentais internos**.

## Ordem recomendada

1. `Tesy_primeira_reuniao_Diana.pptx` — apresentação de 8 slides, ~10–15 min.
2. `GUIAO.md` — guião de fala e respostas curtas para perguntas prováveis.
3. `RESULTADOS_SELECIONADOS.md` — números que podem ser mostrados com segurança e respetivos limites.
4. `REFERENCIAS.md` — referências científicas mínimas para posicionar o trabalho.
5. `data/resultados_apresentacao.csv` — dados usados no gráfico principal.
6. `assets/arquitetura-conceitual.svg` e `assets/resultados-selecionados.svg` — figuras simples reutilizáveis.

## Mensagem central

> O Tesy investiga até que ponto um LLM MoE muito maior do que a VRAM disponível pode ser executado localmente através de routing sparsity, residência dinâmica de experts, execução heterogénea CPU/GPU e storage multi-tier, preservando o routing/top-k/pesos autoritativos.

Não apresentar o projeto como solução terminada nem reclamar novidade ampla. O estado defensável continua `BROAD_NOVELTY_NO_GO / ENGINEERING_AND_MEASUREMENT_GO`.

## O que mostrar

- target físico: Ryzen AI 9 HX 370, RTX 4060 Laptop 8 GiB, 32 GiB RAM, NVMe;
- GPT-OSS 120B MXFP4 como modelo principal de investigação;
- ganhos confirmados de residência de experts em workloads delimitados;
- exemplos de hipóteses rejeitadas quando o ganho não sobreviveu ao caminho completo;
- pergunta de investigação e metodologia de avaliação.

## O que guardar para uma reunião posterior

- patches e detalhes do scheduler;
- IDs Cxxx, ledgers e protocolos completos;
- raw traces e manifests;
- políticas específicas de eviction/prefetch;
- detalhes de branches e do stack histórico;
- claims de novidade antes de prior-art/qualificação final.

## Base documental usada

A pasta foi preparada a partir da branch publicada `campaign/120b-exact-expert-service-20261006T194311Z`, observada em `623a5b97b6e14a39bc671f6d81e7a993a3efe7cb`, incluindo os resultados C129, C142, C274, C282 e C320. O `main` não foi alterado.