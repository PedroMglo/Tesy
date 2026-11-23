# Tesy depois da consolidação de 23 de novembro de 2026

A `main` reúne a fundação 20B, o laboratório 120B até C321, a investigação, a tese e os relatórios LaTeX. O controlo operacional do 120B continua a ser R0 `slots40-persistent`, opt-in. **M3 PARTIAL, M4 NOT_MET.** Há evidência histórica de capacidade acima da RAM e de ganhos de mecanismos concretos. A oportunidade de libertar workers bloqueados continua por demonstrar no pedido completo. [História de C1 a C321](../post-c320/README.md) · [Decisão de arquitetura](../../docs/architecture/0004-servico-exato-de-experts.md) · [Ordem de trabalho para o Codex](PROMPT-CODEX.md)

## Qual fonte prevalece

| Pergunta | Autoridade e consequência da segunda leitura |
|---|---|
| Que resultado 20B é admissível? | A fundação integra a linha numérica A+B e a auditoria independente. A primeira estimativa com base executável irrecuperável conserva `INCONCLUSIVE_EXECUTION_BASE_NOT_PRESERVED`. O ganho de 13,15% refere-se à fronteira de um operador/camada. Um erro relativo máximo de 0,00856, acima da tolerância 0,005 na integração vertical, impediu a qualificação de timing. [Estado da fundação](../../IMPLEMENTATION_STATUS.md) · [Síntese S02](../../docs/research-reports/campaigns/S02-development-branch-synthesis) |
| O que permitiu o progresso do 120B? | C104 isolou trabalho redundante entre waves na mesma build. C129 confirmou melhoria com mais residência, de 32 para 40 slots. C133 obteve 19/20 critérios numa sessão de 20 turnos. C134b qualificou uma recuperação perto da fronteira de contexto. O efeito da capacidade extra, o da agenda e a qualidade têm denominadores diferentes. [Tabela de evidência histórica](../post-c320/README.md) |
| Que desenho já foi eliminado? | C282 isolou a alteração de geometria que confundia a atribuição ao reuso. C293 obteve ganhos parciais aquém do gate global. C318 fechou o staging aprendido após oito braços de custo contemporâneos. C319/C320 fecharam a composição desta família. R2, slots44, EAGLE3 e novos parâmetros de previsão exigiriam uma pergunta causal diferente. [C282](../C282-R2-CAUSAL-QUALIFICATION-CLOSURE-20261005.md) · [C318](../C318-LEARNED-STAGING-COST-NO-GO-20261007.md) · [C320](../C320-EXACT-EXPERT-SERVICE-ARCHITECTURAL-CLOSURE-20261007.md) |
| Como admitir trabalho no portátil? | A política de recursos mais recente deriva limites do dispositivo e valida o arranque. As três propostas anteriores ficaram acessíveis pela história. O launcher conserva caminhos históricos para o modelo e o backend. A presença de receitas e locks numa nova checkout deixa a instalação e as condições físicas atuais como `DESCONHECIDO`. [Política](../../tools/host_resource_policy.py) · [Launcher](../../tools/c143_slots40_optin.py) · [Modelos](../../MODELOS_A_INSTALAR.md) |
| Qual documentação está atualizada para cada uso? | A tese e os relatórios têm datas de corte e decisões editoriais próprias. Os ledgers antigos preservam o que a equipa sabia nessa altura. Para uma decisão atual usar C320/C321, a revisão de novembro e os recibos citados. A release de um PDF exige os bytes visualmente revistos. [Relatórios](../../docs/research-reports/README.md) · [Tese](../../docs/thesis/first-meeting-20261017/README.md) |

## Decode — quanto tempo teria mesmo de desaparecer?

Recalculámos os dois pares AB/BA de cada caso a partir dos oito recibos trace-OFF de C318. A pergunta contrafactual aplica a mesma redução proporcional ao decode de cada braço candidato de um caso, conserva o prefill e o controlo de cada par e mantém o outro caso no seu estado histórico. Para o total, o ganho do par é `1 − (B_total − x × B_decode) / A_total`. Aplicámos as condições de sinal por par, a mediana e a proteção de −5% no outro caso. A tabela dá o limiar de cada via do gate global. Os segundos correspondem à via menos exigente, usando a duração do próprio braço. [Avaliador histórico](../../tools/expert_staging_product_cost_gate.py) · [Cálculo reproduzível](../post-c320/analyse.py)

| Caso | Redução do decode candidato para +8% no total | Redução para +15% no decode | Segundos de decode a recuperar no par AB / BA pela via de +15% |
|---|---:|---:|---:|
| nominal153 | 19,36% | 17,62% | 1,710 / 1,715 s |
| code153 | 27,67% | 18,02% | 2,055 / 2,197 s |

**REPRODUZIDO_MODEL_FREE** para a aritmética e **ESTIMADO** para o cenário. C318 mediu uma regressão mediana no tempo total de 1,86% nominal e 4,01% em código. Duas execuções com igual número de esperas podem ter efeitos opostos na latência. Numa, outra tarefa útil está pronta e atrasa a última barreira. Noutra, todos os restantes consumidores também dependem da leitura pendente. O contador é igual nos dois exemplos e deixa a poupança por identificar. Há quatro workers, sobreposição de leituras, cópia obrigatória e cancelamentos. No nominal, a observação de C317 acrescentou 3,256% ao decode para um limite de 3%. A única forma de usar estas fontes juntas é modelar C317 como diagnóstico e manter C318 como controlo de custo independente. [Observação C317](../C317-LEARNED-OBSERVER-RESULT-20261007.md) · [Recibos C318](../../results/c318-learned-staging-contemporary-product-cost-20261007/paired-cost-analysis.json)

**Decisão.** Reproduzir a agenda bloqueante com os oito journals locais e calcular um intervalo para a continuação. Se os relógios ou a identidade dos workers permitirem duas agendas que conduzem a decisões diferentes, registar ambas, indicar o campo mínimo que as distingue e fechar como `INCONCLUSIVE`. Uma oportunidade que só existe ao assumir coordenação instantânea continua sem admissão a implementação. O critério final é a redução no caminho que chega ao último consumidor do pedido.

## Prefill — qual a pressão inevitável dentro da chamada original?

A fonte C261 contém 36 conjuntos de experts efetivamente pedidos. Para uma camada com união de tamanho U, 40 slots só podem cobrir 40 IDs no início. Nos primeiros cinco tokens podem aparecer no máximo 20 IDs (top-4). Na chamada seguinte de 148 tokens há, por isso, pelo menos `max(0, U − 20 − 40)` admissões no tier primário, mesmo atribuindo os 40 lugares iniciais da forma mais favorável. O cálculo aceita que todas as camadas possam começar com 40 entradas ideais. O payload codificado observado por expert é 13 219 200 B. [Uniões por camada e bytes lógicos](../../results/c261-slots40-prefill-opportunity-20261004/analysis.json)

| Tier | Admissões mínimas em toda a fase | Admissões mínimas demonstráveis só na segunda chamada | Payload correspondente nessa chamada |
|---|---:|---:|---:|
| CPU, 25 camadas | 254 | 19, distribuídas pelas camadas 0/14/15/24 | 251 164 800 B lógicos |
| CUDA0, 11 camadas | 119 | 2, na camada 27 | 26 438 400 B lógicos |

**FORMAL condicionado** ao layout, à capacidade e aos conjuntos deste trace. Este mínimo caracteriza a pressão de residência. Uma admissão pode ser satisfeita por outra cópia já presente. O número de recargas efetivamente elimináveis, o tier físico que as serviria e o tempo crítico exigem outros dados. Para avaliar a segunda hipótese, reconstruir consumidores por tile de R0 dentro da chamada, contabilizar ativações/KV e inspecionar o estado de cache entregue ao decode. Preservar os retornos externos 5+148 e a aritmética nativa ub32. Um controlo com a mesma agenda e a reutilização desativada isola o efeito. [Oportunidade C261](../C261-SLOTS40-PREFILL-OPPORTUNITY-20261004.md) · [Contrato numérico e critérios de paragem](../../docs/architecture/0004-servico-exato-de-experts.md)

## Comparadores e fronteira científica

O produto é uma conversa local útil sob limites de capacidade, qualidade, latência e recursos. O Ollama serve para comparar a experiência final quando ambos admitem o mesmo artefacto e o mesmo trabalho. R0 mede o efeito incremental no Tesy. O llama.cpp contemporâneo oferece um controlo para caches de experts e faltas executadas na CPU. Bevy já descreve partilha de fetches pendentes e concorrência entre pedidos. A investigação do Tesy precisa de identificar quanto serviço autoritativo pode avançar **dentro de uma só conversa** e quanto custa fazê-lo. Mantém-se `BROAD_NOVELTY_NO_GO / ENGINEERING_AND_MEASUREMENT_GO`. [Literatura, versões e limites de comparabilidade](../post-c320/literatura.md) · [Bevy, §4.4](https://arxiv.org/html/2611.04794v1#S4.SS4) · [Upstream llama.cpp](https://github.com/ggml-org/llama.cpp/pull/30966)

## Recuperação do repositório

O [inventário](branches.json) guarda as 45 heads anteriores à fusão, os SHAs e as respetivas árvores. Duas raízes Git independentes ficaram na ancestralidade. Entre os 7 253 caminhos históricos, 7 209 têm representação na localização original e 44 ficaram representados em arquivo com modo e conteúdo idênticos. Houve 152 caminhos com versões concorrentes, num total de 7 533 versões distintas de ficheiros. Estes números dizem respeito às árvores nas 45 heads. A história de commits entre elas também é alcançável. Quatro protótipos incompatíveis ficaram como árvores Git completas e a antiga configuração de releases ficou em arquivo. [Arquivo](../../archive/README.md)

Para verificar num clone completo, a partir da raiz:

```sh
python3 research/consolidacao-20261123/verify.py
python3 research/post-c320/analyse.py
```

O primeiro comando verifica ancestralidade, raízes, árvores, modos, versões dos ficheiros deslocados e identidade dos quatro arquivos. O segundo abre os 13 blobs de origem por OID e também funciona num clone de profundidade 1. Para consultar uma versão antiga usar `git show <SHA>:<caminho>`. Para a recuperar numa branch local usar `git branch <novo-nome> <SHA>` com o SHA do inventário. O clone de um investigador pode conter modelos, journals ou builds fora de Git. A fusão abrange a evidência versionada. **NOT_RUN_RAW_REQUIRED** para o replay integral e **NOT_RUN** para qualquer nova medição física nesta reanálise.
