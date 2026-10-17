# Resultados selecionados — separação entre memória, mecanismo e produto

Este ficheiro é um índice **de claims com âmbito**, não substitui raw/protocolos.

## A. C104 — wave-skip OFF/ON, mesma build
Fonte `research/C104-WAVE-TOGGLE-RESULT-20260928.md`.

- Condição: C75 executável/libraries idênticos entre braços; dois pares alternados, requests completos, mesmo workload e IDs oficiais, início operacional. Page cache não controlada.
- Mediana das reduções de duração com ON: **75,350% no cold prefill**; **27,718% no warm prefill**; cold decode +0,960%, warm decode +7,338%.
- Duração normalizada OFF=100: ON cold **24,650**; ON warm **72,282**.
- Claim: otimização interna real por evitar trabalho desnecessário nas waves, não apenas mais slots. Não prova superioridade cross-backend.
- Limite: C100, comparação C35/C75 entre builds, mediu cold decode **−9,363%** e warm decode **−6,201%** apesar do prefill positivo. Preservar ambos os resultados.

## B. C293 — layout lossless de componentes originais
Fonte `research/C293-INTEGRATED-EXPERT-STORE-COST-NO-GO-20261006.md`.

- Intervenção: disposição e entrega mais contíguas dos pesos originais; router/top-k/payload lógico inalterados.
- Dois pares ABBA por classe; oito processos completos; 33 logits full e argmax bitwise iguais ao controlo R0 gold selecionado; estado inicial completo igual.
- Ganhos medianos emparelhados no custo integrado de trabalho fornecido (153+32): **7,472543%** nominal; **6,048126%** código.
- Prefill: **6,525726% / 6,651285%**; decode: **8,448881% / 5,161119%**, na mesma ordem.
- Claim: organização de dados pode melhorar execução sem mais slots ou alteração dos pesos. Limite: não demonstra melhor resposta livre, nem tráfego NVMe físico ou universalidade.
- O gate interno não promoveu o desenho: isso não transforma ganho medido em regressão.

## C. C271/C273/C282 — expert-major para vários tiles
Fontes `research/C274-BLOCKS-EXPERT-REUSE-CLOSURE-20261004.md` e `research/C282-R2-CAUSAL-QUALIFICATION-CLOSURE-20261005.md`.

- Em trabalho fornecido C271: melhoria mediana **18,189548%** no prefill153; decode mediano **−0,542251%**.
- Em código com geração livre C273: primeiro conteúdo final **8,914968%** mais rápido e resultado validado **5,244724%** mais rápido; dois pares positivos.
- Planeamento C273: candidato concluiu corretamente 2/2; controlo 0/2 (cap); **sem comparação válida de latência até final no controlo**. Perfil R2 gerou trajetória diferente; qualidade geral não herdada.
- Qualificação causal posterior C282: R0→E nominal prefill **+13,12701%**, decode **−10,70339%**; no código prefill **+22,16408%**, decode **+0,63290%**. Perfil R2 não foi promovido.
- Claim: existe potencial de reutilização intra-layer entre tiles, mas o benefício de produto não é geral nem exclusivamente atribuível às recargas porque o perfil mudou também shape de atenção/router.

## D. Mais slots — **não usar como principal contribuição científica**
C129 32→40 e C142 40→44 confirmaram ganhos em workloads delimitados, mas aumentam memória residente e alteram ou podem alterar wave geometry. Úteis para análise do trade-off **capacidade vs desempenho**; não demonstram uma melhoria de eficiência arquitetural a recursos idênticos.

## E. Negativos informativos
C258 EAGLE3 integrado mais lento que autoregressivo nas duas classes; C309/C318 antecipação/staging pior em custo total; C319 Zstd lossless poupança alinhada ~4,3–4,5% na amostra, sem margem para runtime comprimido; C320 fecho com `NO_PROMOTION`.

## Estado
Viabilidade do 120B no portátil: demonstrada no perfil e workloads selecionados. Configuração operacional: `slots40-persistent` opt-in. `M3 PARTIAL` e `M4 NOT_MET`. Não há benchmark externo com igualdade de hardware, quantização, contexto, tarefas e recurso suficientemente abrangente para reclamar superioridade arquitetural geral. A formulação científica deve ser delimitada e os *gates* reavaliados prospectivamente com a orientadora.
