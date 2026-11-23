# Cobertura do repositório e autoridade de cada linha

Fotografia do remoto em 23 de novembro de 2026, antes da branch desta revisão. Foram inventariadas **44 branches**, com 21 na história da fundação e 23 na do laboratório. A referência simbólica `origin/HEAD` apontava para `main`. O índice abaixo fixa cada ponta por SHA e função. A revisão verificou árvores, parentesco, sínteses e falhas anteriores, depois leu as fontes, avaliadores, configurações e recibos que sustentam as decisões. Os milhares de registos derivados e os bytes de cada commit histórico não tiveram uma nova auditoria um a um.

| Linha | O que contém e como a usar |
|---|---|
| [Fundação `main`](https://github.com/PedroMglo/Tesy/tree/7a7d3dcbd1ff8e594ac57459c3db06306083c3ca) | 318 ficheiros no snapshot de 24 set. `src/tesy/` contém o CLI, planeamento, provenance e simuladores. `native/` contém tracer e operadores. `configs/` fixa modelo, backend e máquina. Os ADRs e o ledger desta árvore referem-se à fundação. |
| [Laboratório C321](https://github.com/PedroMglo/Tesy/tree/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb) | 6242 ficheiros. 4938 em `results/`, 740 em `tools/`, 519 em `research/`, 27 em `workloads/`, 12 em `patches/` e 6 na raiz. O launcher, gates de custo/exatidão, workloads, patches de backend e recibos compactos contêm a evidência do 120B. O fecho científico está em C320. C321 regista a sua publicação. |
| [Documentação científica R01/S02](https://github.com/PedroMglo/Tesy/tree/a1f39c84a777b822208f63686657c30d03a38e67/docs/research-reports/campaigns) | O inventário de 30 set. cobria 32 linhas de desenvolvimento entre 40 refs. S02 inclui a atualização até C198. Esta revisão usa também as campanhas posteriores até C321. [Síntese e âmbito](https://github.com/PedroMglo/Tesy/blob/a1f39c84a777b822208f63686657c30d03a38e67/docs/research-reports/campaigns/S02-development-branch-synthesis/sections/01-summary.tex) |
| [Branch da tese](https://github.com/PedroMglo/Tesy/tree/f0938d69def8d494f7f71761e430a4cd3b6588da/docs/thesis) | Descende de C321. Os 24 commits adicionais até 17 out. alteram 12 ficheiros, todos em `docs/thesis/`. A data mais recente desta linha corresponde à documentação. |

A comparação `main...C321` devolve **570 / 775 commits** e nenhuma base comum. As raízes são [`445405f`](https://github.com/PedroMglo/Tesy/commit/445405f619d09f0df5870b8c0238658f4b430ab7) e [`f4fa309`](https://github.com/PedroMglo/Tesy/commit/f4fa309f887006d69e346848ae06156b88759a02). O presente parecer tem base em `main` e cita a história experimental por objetos imutáveis. Uma implementação que dependa dos patches do lab deverá redescobrir o head desse lab e derivar dele a sua branch. Comparar o delta com a base imediata evita importar toda a outra história. As duas árvores de referência não têm gitlinks de submódulo. A reprodução depende dos locks, patches, binários identificados e recibos externos descritos por cada linha.

À abertura da revisão havia um PR aberto, [#41](https://github.com/PedroMglo/Tesy/pull/41), draft na linha independente de documentação, com base `campaign/c3-layer-reference-prefill-20260926-1800utc` em `0cfc1978`. O head era `a1f39c84`, as duas execuções de documentação tinham passado e não havia conversações de revisão por resolver. O corpo mantinha a revisão visual dos PDFs como trabalho pendente. Não há dependência deste PR para a decisão pós-C320.

## Índice das branches

| História | Branch à data da revisão | HEAD | Âmbito auditado |
|---|---|---|---|
| Fundação | `audit/c3-raw-evidence-external-20260925` | [`5a2ac8fb`](https://github.com/PedroMglo/Tesy/tree/5a2ac8fba98d4fe0d32fc43b33b778bc59560ce0) | Primeira tentativa de auditoria de raw externo |
| Fundação | `engineering/full-model-vertical-integration-20260924` | [`ca532aaa`](https://github.com/PedroMglo/Tesy/tree/ca532aaa765ad551dcb8be4424f0abe6778eec96) | Integração vertical 20B e evidência externa |
| Fundação | `engineering/vertical-numerical-blocker-20260924` | [`f4d0a1a7`](https://github.com/PedroMglo/Tesy/tree/f4d0a1a73e437493c77bcef21435631cf792f453) | Bloqueio numérico da camada 2 |
| Fundação | `fix/n3-failclosed-byte-inventory-20260923-v2` | [`95fd92a9`](https://github.com/PedroMglo/Tesy/tree/95fd92a9644f162c4c1bc0c588a0a3897495722d) | Inventário de bytes e proveniência do trace |
| Fundação | `fix/n3-trace-evidence-and-byte-inventory-20260923` | [`11cf607c`](https://github.com/PedroMglo/Tesy/tree/11cf607c3e50257837cb6fb2369788cc5cb7e88d) | Inventário de bytes e proveniência do trace |
| Fundação | `main` | [`7a7d3dcb`](https://github.com/PedroMglo/Tesy/tree/7a7d3dcbd1ff8e594ac57459c3db06306083c3ca) | Fundação, CLI, CI e ADRs |
| Fundação | `research/live-moe-handoff-exactness-20260924` | [`af324ff9`](https://github.com/PedroMglo/Tesy/tree/af324ff9db41038d686cce5e3e5359c8604b7c75) | Exatidão do handoff nativo |
| Fundação | `research/live-moe-handoff-timing-20260924` | [`764cb09a`](https://github.com/PedroMglo/Tesy/tree/764cb09ade02d8b0a40deb7628baab613510ab09) | Custo do handoff nativo |
| Fundação | `research/live-moe-integration-feasibility-20260924` | [`7ab4b9da`](https://github.com/PedroMglo/Tesy/tree/7ab4b9dab72498363aab4e20b94da9486cffacb1) | Fronteira de interceção via cb_eval |
| Fundação | `research/live-moe-reinjection-continuation-exactness-20260924` | [`5fdd1101`](https://github.com/PedroMglo/Tesy/tree/5fdd11016954348405edc9d4ea9fced6dc28c63d) | Reinjeção e continuação numérica |
| Fundação | `research/live-moe-split-graph-skip-exactness-20260924` | [`4e6501fc`](https://github.com/PedroMglo/Tesy/tree/4e6501fc3afaab22bf152fc8e5a9ebb1cd336222) | Split-graph e omissão de trabalho |
| Fundação | `research/mixed-residency-async-overlap-20260924` | [`647a9bc7`](https://github.com/PedroMglo/Tesy/tree/647a9bc77da2b16d2ec2428ec5c0b8723a55ee9d) | Operador misto, overlap e proveniência |
| Fundação | `research/mixed-residency-async-overlap-final-gate-fix-20260924` | [`f33a7070`](https://github.com/PedroMglo/Tesy/tree/f33a7070014406bc9688ac8ac1a6f6476e79a643) | Gate de cauda do operador assíncrono |
| Fundação | `research/mixed-residency-async-tail-order-20260924` | [`cfeea2da`](https://github.com/PedroMglo/Tesy/tree/cfeea2da35f4a5f7c5164902827d009d95cc4001) | Ordem e cauda na execução mista |
| Fundação | `research/n-cpu-moe-capacity-result-20260923T233416Z` | [`cfad9f4c`](https://github.com/PedroMglo/Tesy/tree/cfad9f4c95ebce2124d3f53c83f06469be7e2358) | Evidência de capacidade e admissão física |
| Fundação | `research/n-cpu-moe-fail-20260923T220215Z` | [`88d93d58`](https://github.com/PedroMglo/Tesy/tree/88d93d585155f0dfb22b13039373c7067ae99da8) | Falha inicial da varredura de colocação |
| Fundação | `research/n-cpu-moe-pareto-sweep-20260923` | [`bc430b04`](https://github.com/PedroMglo/Tesy/tree/bc430b0463ece96ebabe90d417a17b9e1e65d57d) | Triagem do continuum CPU-MoE |
| Fundação | `research/n1-passive-router-trace-20260923` | [`3e895e57`](https://github.com/PedroMglo/Tesy/tree/3e895e57e4006635b4482eacd21a5ac28659c427) | Router passivo e inventário GGUF |
| Fundação | `research/numerical-characterization-ab-20260925` | [`7041b39e`](https://github.com/PedroMglo/Tesy/tree/7041b39ec42948e6d394e151974940750ba9b070) | Decomposição A/B de diferenças numéricas |
| Fundação | `research/routed-layer-exactness-20260924` | [`45576ea5`](https://github.com/PedroMglo/Tesy/tree/45576ea5510ecd5cf7149aff75af4a8f42f40077) | Exatidão de uma camada routed |
| Fundação | `research/tesy-causal-residency-20260923` | [`4d1ecd2e`](https://github.com/PedroMglo/Tesy/tree/4d1ecd2e3535eb7b0ecfebfe060737d0dd4138eb) | Hipótese original e bring-up 20B |
| Laboratório | `campaign/120b-assistant-history-sustained-20260928-1123utc` | [`29602ba6`](https://github.com/PedroMglo/Tesy/tree/29602ba6f3be24dc18c73e949e900ca185df1436) | Sessão com histórico, preflight C52b |
| Laboratório | `campaign/120b-block-verifier-expert-reuse-20261004T105527Z` | [`d3fea257`](https://github.com/PedroMglo/Tesy/tree/d3fea2574b8c382827c957b4f835b55882d8b575) | Verificação em bloco e reuso de experts, até C274 |
| Laboratório | `campaign/120b-capacity-and-mechanisms-20260928-1403utc` | [`8f7a07e1`](https://github.com/PedroMglo/Tesy/tree/8f7a07e1db2e526b9f9de30abb86bdda602483f3) | Capacidade, cache e mecanismos, até C154 |
| Laboratório | `campaign/120b-exact-expert-service-20261006T194311Z` | [`623a5b97`](https://github.com/PedroMglo/Tesy/tree/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb) | Política, transporte e antecipação, C283–C321 |
| Laboratório | `campaign/120b-post-c154-residency-20260930T094754Z` | [`8c78f598`](https://github.com/PedroMglo/Tesy/tree/8c78f598e446b1b09fb3ba518b77e0d7496bfa47) | Residência assimétrica, native64 e readiness, até C235 |
| Laboratório | `campaign/120b-r2-causal-qualification-20261005T204839Z` | [`5aec3bbb`](https://github.com/PedroMglo/Tesy/tree/5aec3bbb552aac6a4b176cbb277ec60fc7ff1ccf) | Ablação R2 e restauro persistente de R0 |
| Laboratório | `campaign/120b-session-cost-attribution-20260928-1254utc` | [`fbcb84d0`](https://github.com/PedroMglo/Tesy/tree/fbcb84d0e4e21403c61893b329aa6a6102ca3b55) | Atribuição do custo, interrupção C54 |
| Laboratório | `campaign/c2-correctness-usability-20260926-1349utc` | [`81531d9d`](https://github.com/PedroMglo/Tesy/tree/81531d9dc33caddbbf07928106de47cfe2a6d42a) | Critérios de correctness e piloto de utilidade 120B |
| Laboratório | `campaign/c3-layer-reference-prefill-20260926-1800utc` | [`0cfc1978`](https://github.com/PedroMglo/Tesy/tree/0cfc197836a320709ba0fa8931018728020320b0) | Referência por camada e base das publicações LaTeX |
| Laboratório | `campaign/c4-prefill-cost-20260927-0022utc` | [`85424b63`](https://github.com/PedroMglo/Tesy/tree/85424b63a238d50e340b4aad6525e33d7e9d7da3) | Custo de prefill |
| Laboratório | `campaign/c5-first-divergence-20260927-0147utc` | [`9426492d`](https://github.com/PedroMglo/Tesy/tree/9426492db4faeb3f5765af24938bd4fb4d8708f6) | Localização da primeira divergência |
| Laboratório | `campaign/c6-attn-dispatch-compat-20260927-0301utc` | [`0047a050`](https://github.com/PedroMglo/Tesy/tree/0047a050803c29ea928022e7d3e8ba035fedb866) | Compatibilidade numérica do dispatch de atenção |
| Laboratório | `ci/automatic-report-releases-20260927` | [`cc9eb8ba`](https://github.com/PedroMglo/Tesy/tree/cc9eb8ba5dc6add4d5132a37ebed3212bf533c62) | Relatórios em releases automáticas |
| Laboratório | `ci/publish-all-latex-reports-20260927` | [`71413344`](https://github.com/PedroMglo/Tesy/tree/7141334475bed4a338971ce504a42f8ad4c3364b) | Publicação de todos os PDFs LaTeX |
| Laboratório | `docs/report-pdf-delivery-20260927` | [`74132c77`](https://github.com/PedroMglo/Tesy/tree/74132c77c539476996d3f58c2ccb3430827af9ad) | Build e entrega de PDFs |
| Laboratório | `docs/reporting-coverage-gate-20260927` | [`9b513d4e`](https://github.com/PedroMglo/Tesy/tree/9b513d4e1c0654176b65b50e917ea016d1d38048) | Cobertura e revisão da evidência publicada |
| Laboratório | `docs/research-reports-c3-lab-20260927` | [`68d71885`](https://github.com/PedroMglo/Tesy/tree/68d71885539172615d3b753530dc08e40e81273b) | Relatórios congelados no ramo C3 |
| Laboratório | `docs/scientific-literature-c4-c6-20260928` | [`a1f39c84`](https://github.com/PedroMglo/Tesy/tree/a1f39c84a777b822208f63686657c30d03a38e67) | Literatura, síntese R01/S02 e cobertura C4–C6 |
| Laboratório | `docs/thesis-first-meeting-20261017` | [`f0938d69`](https://github.com/PedroMglo/Tesy/tree/f0938d69def8d494f7f71761e430a4cd3b6588da) | Síntese de tese e apresentação |
| Laboratório | `fix/prospective-resource-policy-20260928` | [`33a40c03`](https://github.com/PedroMglo/Tesy/tree/33a40c034a76bca7205efa702b8b74daa63a4736) | Admissão de recursos e regras de sessão |
| Laboratório | `fix/prospective-resource-policy-handoff-20260928` | [`1cd1a6dc`](https://github.com/PedroMglo/Tesy/tree/1cd1a6dc610abaa237a42a57b60881472719b6c1) | Admissão de recursos e regras de sessão |
| Laboratório | `fix/prospective-resource-policy-squashed-20260928` | [`8cd947ac`](https://github.com/PedroMglo/Tesy/tree/8cd947aca239c45de5669a657a1e1ad0caa96f28) | Admissão de recursos e regras de sessão |
| Laboratório | `scale-lab` | [`c67529e2`](https://github.com/PedroMglo/Tesy/tree/c67529e290844bb3d9033615072d5878014a46bc) | Primeiro laboratório de streaming, 24/32 slots |

## Roteiro de leitura da implementação

1. Para reproduzir R0, partir do [launcher persistente](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/tools/c143_slots40_optin.py) e da [receita C281](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C281-PERSISTENT-R0-RESTORATION-RESULT-20261005.md). Verificar as dependências atuais e o host antes de qualquer execução real.
2. Para compreender o custo de antecipação, cruzar o [patch dos workers](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/patches/c305-cpu-prediction-staging.patch), o [cliente que escolhe os pontos de medição](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/tools/expert_learned_staging.cpp), o [avaliador ABBA](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/tools/expert_staging_product_cost_gate.py) e os [recibos C318](https://github.com/PedroMglo/Tesy/tree/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/results/c318-learned-staging-contemporary-product-cost-20261007).
3. Para a hipótese de prefill, ler o [inventário C261](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/results/c261-slots40-prefill-opportunity-20261004/analysis.json), o [contrato C262](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C262-LAYER-EXPERT-REUSE-NUMERIC-FREEZE-20261004.md), o [gate R2](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/tools/r2_causal_gate.py) e o [fecho C282](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C282-R2-CAUSAL-QUALIFICATION-CLOSURE-20261005.md). A [decisão pós-C320](../../docs/architecture/0004-servico-exato-de-experts.md) define o contraste novo.
4. Para localizar os dados que só existem no portátil, usar o [índice C320](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/results/c320-exact-expert-service-closure-20261007/raw-index.json) e o [handoff C321](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/research/C321-PUBLICATION-SHUTDOWN-HANDOFF-20261007.md). O [analisador](analyse.py) publica um inventário mínimo com caminhos, tamanhos e hashes para a primeira pergunta.

## Como conferir a topologia

Num clone com as refs publicadas, os comandos seguintes permitem repetir o inventário. `git merge-base` devolve código 1 para as duas histórias sem ancestral comum. O futuro número de branches pode mudar, pelo que os SHAs acima definem esta fotografia.

```sh
git ls-remote --heads origin
git rev-list --max-parents=0 7a7d3dcbd1ff8e594ac57459c3db06306083c3ca 623a5b97b6e14a39bc671f6d81e7a993a3efe7cb
git rev-list --left-right --count 7a7d3dcbd1ff8e594ac57459c3db06306083c3ca...623a5b97b6e14a39bc671f6d81e7a993a3efe7cb
git merge-base 7a7d3dcbd1ff8e594ac57459c3db06306083c3ca 623a5b97b6e14a39bc671f6d81e7a993a3efe7cb
git diff --name-only 623a5b97b6e14a39bc671f6d81e7a993a3efe7cb f0938d69def8d494f7f71761e430a4cd3b6588da
```
