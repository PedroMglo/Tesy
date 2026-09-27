# TESY — Especificação de implementação do sistema de relatórios científicos

**Versão:** 1.0
**Data da revisão:** 2026-09-26
**Estado deste documento:** PROPOSED — especificação; não é uma implementação nem um relatório experimental validado.
**Destino proposto no repositório:** `docs/research-reports/IMPLEMENTATION-SPEC.md`

## 1. Objetivo e limites desta entrega

Implementar um formato LaTeX estável para documentar campanhas do Tesy, incluindo progresso, resultados negativos, correções, evidência e decisões, com leitura adequada a futuros orientadores de tese. Toda a camada documental deve ficar sob `docs/research-reports/`.

Este documento desenvolve o plano anexado pelo utilizador. As alterações ao plano são identificadas como decisões propostas; não são apresentadas como requisitos já existentes no Tesy. Foram consultados ficheiros selecionados do repositório, não realizada uma auditoria integral de todo o código, branches ou logs.

Nesta revisão não foram executados modelos, reanalisados logs brutos, recalculados os hashes dos ficheiros originais do Git nem compilado um template LaTeX. Não se alterou o repositório remoto. Os valores experimentais abaixo são os publicados nas fontes consultadas, não novas medições.

A consulta de `main` devolveu `7a7d3dcbd1ff8e594ac57459c3db06306083c3ca`. Para a Campanha 2, a revisão usou exclusivamente a fotografia documental `81531d9dc33caddbbf07928106de47cfe2a6d42a`. Não se deve assumir que esse conteúdo existe em `main`, nem substituir o SHA por uma branch móvel.

## 2. Fontes consultadas e autoridade

| Ref. | Fonte | Revisão / utilização |
|---|---|---|
| U1 | `Pasted text(20260926-224103).txt` | Plano fornecido pelo utilizador; base de organização, não evidência experimental primária. |
| R1 | `AGENTS.md` | Lido em `main`; contrato de honestidade, distinção de claims, limites de repositório e publicação. |
| R2 | `results/INDEX.md` | C2 no SHA congelado; autoridade explícita e relações entre snapshots, análises e correções. |
| R3 | `results/c2-final-summary.json` | C2 no SHA congelado; resumo estruturado e estado global. |
| R4 | `research/C2-FINAL-20260926.md` | C2 no SHA congelado; narrativa autoritativa, metodologia, limites e decisões. |
| R5 | `results/c2c-target32-sustained01.gate.json` | C2 no SHA congelado; valores e PASS do gate de timing/recursos C2-C. |
| R6 | `research/PLAN-AUDIT-20260926.md` | Cópia no SHA C2; auditoria final de C1 e limites históricos. Não substitui uma futura identificação do snapshot original de C1. |
| T1 | RFC 6901, JSON Pointer | Sintaxe para localizar um valor específico dentro de um JSON. |
| T2 | CTAN, `latexmk` | Automatização da sequência de compilação LaTeX. |
| T3 | Reproducible Builds, `SOURCE_DATE_EPOCH` | Controlo de timestamps; não constitui, isoladamente, prova de PDF idêntico byte a byte. |

Localizadores verificáveis, em formato de código:

```text
https://github.com/PedroMglo/Tesy/blob/main/AGENTS.md
https://api.github.com/repos/PedroMglo/Tesy/branches/main
https://github.com/PedroMglo/Tesy/blob/81531d9dc33caddbbf07928106de47cfe2a6d42a/results/INDEX.md
https://github.com/PedroMglo/Tesy/blob/81531d9dc33caddbbf07928106de47cfe2a6d42a/results/c2-final-summary.json
https://github.com/PedroMglo/Tesy/blob/81531d9dc33caddbbf07928106de47cfe2a6d42a/research/C2-FINAL-20260926.md
https://github.com/PedroMglo/Tesy/blob/81531d9dc33caddbbf07928106de47cfe2a6d42a/results/c2c-target32-sustained01.gate.json
https://github.com/PedroMglo/Tesy/blob/81531d9dc33caddbbf07928106de47cfe2a6d42a/research/PLAN-AUDIT-20260926.md
https://www.rfc-editor.org/rfc/rfc6901
https://ctan.org/pkg/latexmk
https://reproducible-builds.org/docs/source-date-epoch/
```

Para implementar, reler o contrato aplicável à árvore efetivamente usada. A tentativa de ler `AGENTS.md` diretamente no SHA C2 devolveu 404 nesta sessão; o contrato consultado foi o de `main`. Não criar a ficção de que todos os documentos pertencem à mesma árvore.

### 2.1 A autoridade não é uma pasta única

Manter `research/` como registo narrativo experimental, mas não dizer que é a única fonte de verdade. O registo de autoridade deve relacionar protocolos, resultados estruturados em `results/`, manifests, decisões, correções e narrativas. A precedência deve ser por claim e por finalidade, não uma regra cega de JSON contra Markdown.

R2 identifica o `campaign-summary.json` como snapshot inicial imutável de C1. Identifica ainda o gate C2-C e `analysis-v2` como fontes autoritativas para funções diferentes; a análise anterior contém um erro de chave de eventos. Estes exemplos devem tornar-se testes de regressão do sistema documental.

Não selecionar ficheiros por data de modificação, ordenação alfabética ou nome mais recente. Quando fontes autoritativas divergirem sobre o mesmo claim, bloquear esse claim/publicação, produzir um relatório da divergência e exigir resolução explícita. Não corrigir a fonte experimental a partir do PDF.

## 3. Alterações necessárias ao plano original

### 3.1 Separar identidades

Registar separadamente:

- `experiment_identity`: commit/tree do código efetivamente executado, por run quando necessário; backend, binário, bibliotecas, modelo, tokenizer, protocolo e workload.
- `evidence_snapshot_commit`: revisão imutável onde se obtêm os documentos e resultados usados pelo relatório.
- `report_source_identity`: revisão e/ou digest determinístico do conjunto de fontes do relatório e ferramentas de transformação.
- `build_identity`: versões efetivas de motor, pacotes, Python, fontes tipográficas, configuração e opções de compilação.

R3 distingue `base_lab_commit=c67529e...`, `last_measured_code_commit=39f958c...` e o snapshot documental usado nesta revisão (`81531d9...`). Não os comprimir num campo ambíguo chamado `commit`.

Evitar autorreferência: o manifesto de build e os PDFs não entram no digest que eles próprios registam. Se o relatório estiver em preparação num worktree, identificar o conjunto de fontes e o estado dirty; não exigir inserir no ficheiro o SHA do commit que irá conter esse mesmo ficheiro.

### 3.2 Separar classificações

Conservar sempre os rótulos originais das fontes e só depois oferecer uma normalização documentada.

| Dimensão | Exemplos propostos | Significado |
|---|---|---|
| Classe de evidência | MEDIDO, REPRODUZIDO, ESTIMADO, INFERIDO, HIPÓTESE, DIAGNÓSTICO, DESCONHECIDO | Como se sustenta a afirmação. |
| Estado de execução | COMPLETED, FAILED, ABORTED, NOT_RUN | O que aconteceu à experiência. |
| Resultado do contrato | PASS, FAIL, BLOCKED, NOT_VALIDATED | Resultado de um gate nomeado, nunca de tudo implicitamente. |
| Validade histórica | ACTIVE, SUPERSEDED, WITHDRAWN | Se o claim permanece utilizável e em que âmbito. |
| Disponibilidade | TRACKED_SOURCE_AVAILABLE, LOCAL_RAW_NOT_ACCESSED, MISSING | O que o leitor/verificador realmente pode consultar. |
| Estado editorial | DRAFT, REVIEWED, RELEASED, SUPERSEDED | Maturidade e publicação do documento. |

`NOT_RUN` não é uma classe de evidência; `FAIL` não significa que a medição não ocorreu; `MEDIDO` não equivale a `PASS`. Incluir HIPÓTESE, presente no contrato R1 mas ausente das macros propostas no anexo.

### 3.3 Publicação pode ter resultado científico negativo

Um relatório pode estar editorialmente pronto e descrever uma campanha `CORRECTNESS_BLOCKED`. A publicação só é impedida por problemas documentais relevantes: fontes requeridas em falta, divergências por resolver, referências quebradas, claims sem suporte, privacidade ou build inválido. Um resultado negativo não deve impedir a sua documentação.

### 3.4 Hashes não demonstram toda a cadeia

Distinguir hash esperado, hash efetivamente calculado e origem do hash esperado. O SHA de um blob Git não é o SHA-256 do conteúdo experimental. Calcular sobre bytes originais, não sobre uma representação JSON reformatada nem sobre a resposta textual do conector.

R4 diz que logs, respostas e linhas de logits ficaram locais; o Git contém publicações compactas e hashes. Assim, verificação de fontes versionadas pode passar enquanto a reanálise dos dados brutos fica `NOT_RUN`. Nunca rotular esse resultado como reprodução experimental completa.

## 4. Estrutura mínima proposta

```text
docs/research-reports/
├── README.md
├── IMPLEMENTATION-SPEC.md
├── registry.json
├── schema/
│   ├── campaign.schema.json
│   ├── evidence.schema.json
│   └── release.schema.json
├── template/
│   ├── tesyresearch.cls
│   ├── macros.tex
│   ├── campaign-template.tex
│   └── sections/
├── shared/
│   ├── bibliography.bib
│   └── styles/
├── tools/
│   ├── new_campaign.py
│   ├── verify_evidence.py
│   ├── derive_report_data.py
│   └── build_report.py
├── tests/
│   └── fixtures/
├── campaigns/
│   └── C02-correctness-usability/
│       ├── campaign.json
│       ├── evidence-spec.json
│       ├── evidence-lock.json
│       ├── report.tex
│       ├── sections/
│       ├── generated/
│       ├── audit.md
│       └── CHANGELOG.md
├── dossier/
├── published/
└── _build/
```

`campaign.json` é a autoridade dos metadados editoriais. `metadata.tex`, métricas, tabelas e CSV são gerados; não manter duas cópias editáveis dos mesmos números/metadados. A classe é fina, preferencialmente apoiada numa classe LaTeX existente, sem regras específicas para C2.

`generated/` contém saídas derivadas marcadas como não editáveis, acompanhadas do digest das entradas e da versão do adaptador. `_build/` contém temporários ignorados por Git. Não copiar pesos, logs privados nem fontes tipográficas para distribuição.

`published/` é sempre o destino local dos PDFs. A política inicial proposta é não versionar automaticamente binários gerados. Uma publicação selecionada pode ser distribuída depois de decisão explícita, com nome versionado e manifesto. Isto evita contrariar R1, que exclui artefactos gerados grandes. Não criar um workflow de publicação remota nesta primeira etapa.

## 5. Contrato de evidência e transformações

### 5.1 Separar a especificação do lock

`evidence-spec.json` declara o que extrair: ID, caminho e revisão, papel da fonte, seletor, unidade, fórmula, condições, classe original, âmbito, status e limitações.

`evidence-lock.json` regista a resolução verificável dessa especificação: hashes calculados, revisões resolvidas, entradas utilizadas, versão do adaptador, resultado de integridade e disponibilidade. A ausência de uma fonte obrigatória é um erro explícito; não deve produzir zero nem uma string vazia que pareça um valor medido.

Os IDs são estáveis: `E-C2-001` pode identificar uma entrada de evidência e `CL-C2-SUSTAINED-DECODE` um claim. Uma fonte pode apoiar vários claims, e um claim pode exigir várias fontes.

Para valores JSON, usar JSON Pointer conforme T1. Para evidência textual, usar ficheiro completo identificado por hash e localização humana (secção/linhas), conservando uma transcrição explícita e revisada quando não existir uma fonte estruturada adequada. Não criar um parser universal de Markdown para fingir ausência de trabalho editorial.

### 5.2 Exemplo concreto de ligação, ainda não um lock validado

```json
{
  "claim_id": "CL-C2-SUSTAINED-DECODE",
  "evidence_snapshot_commit": "81531d9dc33caddbbf07928106de47cfe2a6d42a",
  "source_path": "results/c2c-target32-sustained01.gate.json",
  "source_selector": "/decode_tok_s",
  "expected_sha256_from_summary": "0e27140bfee84ef9bb68dbf04c21ca44c652c99959762fcb701651ea1069f7c0",
  "expected_hash_source": "results/c2-final-summary.json",
  "hash_verification_in_this_review": "NOT_RUN",
  "run_id": "c2c-target32-sustained01",
  "unit": "token/s",
  "published_value": 3.326787581473213,
  "display_decimal_places": 3,
  "aggregation": "sum(decode_tokens) / sum(decode_seconds)",
  "evidence_class_original": "MEDIDO_NO_TARGET",
  "scope": "C2-C timing/resource protocol; 20 requests in one process",
  "forbidden_extension": "Does not establish independent long-prefix numerical parity for GPU8/32"
}
```

O hash esperado acima foi lido de R3, não recalculado nesta revisão. A implementação deve verificá-lo sobre os bytes obtidos da revisão indicada. Verificar também que o valor do gate coincide com o resumo e com a recomputação declarada, utilizando uma tolerância numérica explícita, sem tratar um problema de representação decimal como alteração experimental.

### 5.3 Regras de transformação

Preservar valores brutos e unidades. Arredondar apenas na apresentação. A fórmula deve constar do registo derivado. Não usar média aritmética de taxas por pedido como substituto de `sum(tokens)/sum(seconds)`.

Contar unidades experimentais corretamente: R4 descreve um processo com vinte pedidos para C2-C. Isso não é automaticamente vinte repetições independentes. Não inventar intervalos de confiança, barras de erro, desvios padrão, p50/p95 ou significância.

Uma divergência deve produzir um diagnóstico com os ficheiros e valores em conflito. Não alterar thresholds nem retirar casos falhados para obter PASS documental ou científico.

## 6. Esqueleto fixo de cada relatório

Manter a ordem do plano original, mas integrar capa e resumo na primeira página útil, sem uma capa decorativa vazia.

| Secção | Requisito |
|---|---|
| Identificação e Executive Summary | Campanha, pergunta, estado global original, estado editorial, resultados centrais, limites e próximo gate. |
| Research Question | Hipótese, objetivo e natureza confirmatória/exploratória/retrospetiva. |
| Context | Evidência disponível antes da campanha, sem usar retroativamente conhecimento posterior. |
| Experimental Contract | Modelo, hardware observado, backend, workloads, thresholds, budget, critérios de paragem e protocolo congelado. |
| Methodology | Baseline/candidate, identidade das execuções, instrumentação, métricas, fórmulas e limites dos sensores. |
| Results | Resultados por gate, com unidade, âmbito e evidência. |
| Failed Experiments | Inventário de falhas, abortos, timeouts, resultados inválidos/retirados e NOT_RUN relevantes. |
| Interpretation | Inferências identificadas e alternativas explicativas. |
| Limitations & Claim Boundary | O que foi e não foi demonstrado; sem propagação de validade entre modelos/configurações. |
| Decision | Decisão contemporânea, critérios usados e eventual reavaliação posterior em bloco separado. |
| Next Discriminating Gate | Experiência que distingue hipóteses; não uma promessa de resultado. |
| Appendices | Comandos, identidades, índice de evidência, cronologia, disponibilidade dos dados e tabelas completas. |

Uma secção sem dados deve dizer `NOT_RUN`, `NOT_MEASURED`, `UNKNOWN` ou `NOT_APPLICABLE`, conforme o caso e com justificação. Não a apagar silenciosamente.

Acrescentar um glossário curto para termos internos, incluindo GPU8 = oito camadas colocadas na GPU, slots por camada, prefill, decode, first text e first final. Não tratar estes rótulos como autoexplicativos para um orientador.

Idioma: parametrizável. A proposta editorial é relatório técnico em inglês com resumo português opcional; não duplicar integralmente o documento. Não inventar universidade, orientador, afiliação ou aprovação científica. O autor deve ser preenchido pelo responsável.

## 7. Piloto C2: valores e fronteiras que não podem desaparecer

Dados lidos de R3–R5; conversões indicadas são aritmética sobre os valores publicados.

| Elemento | Valor / tratamento obrigatório |
|---|---|
| Estado global | `CORRECTNESS_BLOCKED`, copiado da fonte. |
| Decode C2-C | 4588 tokens / 1379.10819 s = 3.326787581473213 token/s; apresentar 3.327. |
| Segunda metade | 3.289639775697045 token/s; preservar definição da fonte. |
| Unidade experimental | 20 pedidos, um processo; não vinte repetições independentes. |
| Duração | Separar wall time, active time e decode time; não dizer que todo o wall time foi decode ininterrupto. |
| Memória C2-C | `memory.peak` do cgroup: 15,344,664,576 B = 14.29083251953125 GiB. Não chamar RAM total do host ou RSS. |
| Limite de memória | 18 GiB; swap máximo zero. |
| GPU C2-C | Pico publicado de 3856 MiB; não usar o pico de C2-E por engano. |
| GPU C2-E | Pico publicado de 3858 MiB, referente a outro run. |
| Guard GPU | 7000 MiB = 6.8359375 GiB; não substituir por 7 GiB. |
| Modelo | Ficheiro selecionado com 63,387,346,208 B = 63.387346208 GB; quantização/formato MXFP4 GGUF. Não generalizar a pesos em outra precisão. |
| Latência curta | First text 42.309152927999094 s; first final 74.50597923299938 s. Não fundir as duas definições num TTFT genérico. |
| Utilidade | 12/12 no alvo e 10/12 no stock20B; uma execução por caso e modelo na suite sintética c2eval12. |
| Custo da utilidade | Soma de wall time dos pedidos: 3058.1746355689975 s / 266.43963020500814 s = razão publicada 11.47792703816594. |
| Âmbito das duas vitórias | Casos em que stock atingiu o cap de 2048 tokens em reasoning sem final; não é superioridade geral do modelo. |
| Correção numérica | GPU8/32 long-prefix `NOT_VALIDATED`; referência histórica é uma única linha final de logits após quatro token IDs. |
| Referências 120B | Duas tentativas terminaram no RSS guard; não transformar linhas parciais em aprovação completa. |
| Operação | Contexto configurado 4096; os três prompts multiturn efetivamente observados foram 86, 663 e 2150 tokens; fronteira de prompt 4096 `NOT_RUN`. |
| I/O | Tráfego NVMe físico exclusivo desconhecido. `process read_bytes` não é essa medição. |
| Controlo 24 slots | Não existe novo controlo sustentado 24 slots com o mesmo protocolo C2. |
| Comparação histórica | C1 sustentado: 2.733 token/s (R6); não fundir com médias de ensaios curtos 16/24/32. |

No corpo, distinguir `PASS` do gate de timing/recursos e falha dos objetivos >=4 token/s e latência curta. As respostas funcionais C2-E não provam igualdade numérica para todos os prefixes percorridos.

A referência a "32 GiB de RAM" deve distinguir configuração nominal de hardware de R1 da RAM reportada no registo observado de R4. Não apresentar a memória livre no arranque de uma campanha passada como estado atual da máquina.

## 8. Figuras e tabelas

Começar com poucos elementos que respondam a perguntas concretas. Não exigir gráficos para todas as secções nem preencher espaço com desenhos científicos aparentes.

### 8.1 Matriz de cobertura de correção

Linhas por teste/contrato; colunas ou cabeçalhos identificam modelo, placement, cache, prefixo e referência. Evitar misturar `20B`, `120B` e `GPU8/32` como categorias equivalentes: os dois primeiros são modelos e o terceiro é configuração. Cada PASS exige evidência do âmbito exato. Os PASS do esquema ilustrativo do anexo não podem ser copiados sem validação.

### 8.2 Latência por comprimento de prompt

Usar 113/496/1522 tokens com prefill 41.353/146.961/447.076 s e as definições separadas de first text e first final de R4. Pontos medidos e legenda descritiva, sem extrapolar para 250k tokens nem diagnosticar causalmente um subsistema. O tempo observado localiza a espera; não demonstra sozinho o mecanismo dominante.

### 8.3 Orçamento de recursos

Comparar pico observado e limite do mesmo âmbito: cgroup com cgroup, GPU com GPU. Converter unidades a partir de bytes quando disponíveis. Separar C2-C e C2-E. As legendas dizem se a métrica é um pico do cgroup ou máximo de amostras, e quais são os limites de resolução temporal.

### 8.4 Utilidade e custo

Preferir uma tabela compacta: ambos passam, só alvo passa, só stock passa, falhas, cap e tempo total. Um gráfico com dois pontos não deve sugerir fronteira de qualidade geral ou significância. Dar visibilidade ao custo 11.478x e ao cap das respostas.

### 8.5 Evolução entre campanhas

Distinguir no estilo e legenda: A/B emparelhado, ensaio curto, sustentado e comparação histórica. Só apresentar uma razão como efeito causal de alterar slots quando os protocolos comparáveis a sustentarem. C1 e C2 podem aparecer juntos, mas não numa linha de "speedup 24→32" falsamente controlada.

### 8.6 Cronologia

Usar timestamps de fontes ou uma simples ordem de marcos. Nunca inventar durações ou sugerir semanas de trabalho quando as datas das campanhas não o sustentam. Mostrar correções e retirada de claims em vez de substituir eventos antigos.

## 9. LaTeX e legibilidade

Manter as escolhas do plano: LuaLaTeX, latexmk, booktabs, tabularx/longtable, siunitx, pgfplots, microtype, hyperref, cleveref; usar tcolorbox/TikZ quando realmente necessários. A bibliografia usa biblatex/biber quando há literatura efetivamente citada. Não gerar referências fictícias para completar uma secção.

Design: A4, hierarquia simples, uma cor de destaque, rótulos textuais para estados, tabelas legíveis, gráficos vetoriais, rodapé com ID/versão e identidade documental abreviada. O SHA completo e identidades experimentais ficam no índice. O documento deve funcionar a preto e branco. Não distribuir ficheiros de fontes tipográficas.

A classe e o template não devem depender de C2. IDs/valores/estado entram por dados, não por condições ad hoc como `if campaign == C2` no styling.

Separar literatura externa e evidência interna, mantendo ligações explícitas entre texto e índice de evidência. A separação é uma convenção documental proposta, não uma afirmação de que fontes internas nunca possam ser citadas academicamente.

APIs sugeridas: `\metric{ID}`, `\claim{ID}{texto}`, `\evidence{ID}`, `\EvidenceHypothesis{texto}`, `\StatusBlocked`. O verificador pode garantir existência de IDs e consistência de valores; não pode demonstrar automaticamente a correção semântica de toda a prosa livre.

## 10. Pipeline de verificação e build

```text
fontes explícitas em revisões imutáveis
    → verificar bytes, hashes, seletores, unidades e relações de autoridade
    → produzir dados normalizados e registo de limitações
    → gerar métricas, tabelas, CSV e índice de evidência
    → compilar o relatório
    → auditar referências, valores, limites e layout
    → produzir PDF versionado e manifesto de publicação
```

Comandos propostos, a implementar — não existem por força desta especificação:

```bash
python docs/research-reports/tools/new_campaign.py C03-nome --status draft
python docs/research-reports/tools/verify_evidence.py C02-correctness-usability --scope tracked
python docs/research-reports/tools/derive_report_data.py C02-correctness-usability
python docs/research-reports/tools/build_report.py C02-correctness-usability --mode draft
python docs/research-reports/tools/build_report.py C02-correctness-usability --mode release
```

A resolução de fontes pode usar `git show <sha>:<path>` sem mudar a branch de trabalho. Não fazer reset, rebase ou checkout destrutivo. O SHA em falta produz um diagnóstico específico, não fallback para `main`/HEAD. Um modo de aquisição explícito pode ser implementado separadamente, mas uma compilação não deve depender de rede silenciosamente.

Escapar textos para LaTeX, validar IDs, bloquear paths fora das raízes permitidas e não executar comandos provenientes de dados. Sem shell-escape por omissão. A construção do relatório não deve abrir serviços de inferência nem iniciar downloads de modelos.

### 10.1 Quatro verificações diferentes

1. Integridade documental: os ficheiros consultados correspondem ao lock.
2. Regeração de derivados: as mesmas entradas e fórmulas produzem as mesmas métricas/tabelas/CSV.
3. Build do PDF: o documento compila com referências resolvidas e layout revisto.
4. Reprodução experimental: nova execução ou reanálise de dados brutos, apenas quando realmente realizada.

Reportar cada resultado separadamente. Para C2 neste estágio, é possível implementar 1–3 usando publicações compactas, mas 4 não se torna verdadeiro automaticamente.

### 10.2 Reprodutibilidade do PDF

`latexmk` automatiza a sequência de compilação (T2); isso não é uma garantia de bytes idênticos. Fixar e registar toolchain, fontes tipográficas, locale, opções, dados e timestamps. `SOURCE_DATE_EPOCH` pode participar no controlo temporal (T3), mas deve ser testado no motor usado.

Critério proposto: dois builds limpos em diretórios diferentes; comparar hashes dos derivados e do PDF. Só escrever `BYTE_REPRODUCIBLE` se a comparação passar no ambiente identificado. Se o conteúdo coincidir mas os bytes diferirem, declarar a diferença e investigar; não renomear esse estado como reprodução bitwise. Não generalizar o teste a todos os sistemas operativos.

Separar o instante real de execução do build, guardado num registo externo, dos metadados determinísticos do PDF. Não introduzir Docker/containerização para resolver isto sem o ADR exigido por R1. Registar versões disponíveis e compatíveis em vez de inventar pins ou atualizar instalações partilhadas.

## 11. Testes de aceitação que interessam

Os testes devem ser documentais e rápidos; nenhum exige executar o 120B.

| Teste | Resultado esperado |
|---|---|
| Alterar um byte de uma fonte bloqueada por hash | Verificação falha com fonte identificada. |
| Selecionar `campaign-summary.json` como resumo final C2 | Seleção rejeitada por autoridade/identidade. |
| Usar a análise C2-C anterior para detalhes corrigidos | Rejeitado ou só permitido em secção histórica explícita. |
| JSON Pointer inexistente | Erro; nunca zero/placeholder silencioso. |
| JSON com chaves duplicadas ou números não finitos | Erro de parsing/validação para fonte numérica. |
| Trocar bytes, GB e GiB | Teste deteta conversão/label incorreto. |
| Trocar média de taxas por razão de somas | Fixture evidencia a diferença. |
| ID duplicado ou referência inexistente | Build de release bloqueado. |
| Raw data local não disponível | Estado de disponibilidade visível; não alegar reanálise. |
| Campanha científica FAIL/BLOCKED bem documentada | PDF válido; sem promoção para PASS. |
| Claim WITHDRAWN usado como resultado atual | Release bloqueado ou claim limitado a histórico claramente assinalado. |
| Regeração após alterar entradas | Derivados desatualizados detetados. |
| Texto com `_`, `%`, `&`, Unicode e paths longos | Compilação e layout corretos. |
| Segunda campanha | Mesma classe/estrutura; sem fork C1 da classe. |
| Dois builds limpos | Derivados iguais; estado de igualdade do PDF registado honestamente. |
| Ficheiros temporários/privados/pesos | Não entram no pacote/publicação. |

Uma verificação automática de strings proibidas não substitui revisão científica. O relatório de auditoria deve incluir uma matriz manual claim → evidência → limite, com discrepâncias ou omissões descobertas.

## 12. Fases, entregáveis e critérios de saída

### A — Contrato e fontes

Entregar README, estrutura, schemas, política de estados/publicação, mapa de fontes e identidade do snapshot C2. Saída: fonte autoritativa definida para cada família de claims materiais e nenhuma ambiguidade escondida.

### B — Template mínimo e dados derivados

Entregar classe fina, macros, secções fixas, estilos, gerador de campanha e adaptador C2. Os fixtures demonstrativos usam dados claramente sintéticos e não se confundem com C2. Saída: exemplo compila e estados negativos/missing são legíveis.

### C — Relatório piloto C2

Entregar PDF, fontes, tabelas/gráficos derivados, evidence lock e auditoria. Saída: todos os valores materiais possuem origem/transformação; `CORRECTNESS_BLOCKED`, objetivos falhados, limitações de utility e fonte `analysis-v2` estão preservados. Não correr modelos para preencher lacunas.

### D — Auditoria adversarial

Executar os testes documentais e revisão visual de todas as páginas. Conferir cobertura dos eventos negativos materiais descritos nas fontes selecionadas, sem afirmar inventário completo dos raws inacessíveis. Saída: falhas documentais resolvidas ou explicitamente impeditivas; estado de reprodução dos dados brutos separado.

### E — Generalização C1

Identificar as fontes originais e produzir C1 com a mesma classe. R6 aponta a narrativa final, mas deve ser verificado o snapshot histórico adequado antes de fechar o relatório. Preservar `SUCCESS` no âmbito original, o empate 8/10, M2 parcial e as falhas históricas. Não aplicar retroativamente a classificação C2 nem transferir validação de C2 para C1.

### F — Fundação e dossier

Depois de C1/C2, reunir fontes para R00 e produzir síntese cumulativa. Não converter todos os pequenos gates em relatórios autónomos. O dossier deve referenciar versões específicas dos relatórios e declarar a sua data de corte.

Alteração editorial proposta ao anexo: preparar primeiro uma síntese de orientação de cerca de 8–12 páginas, não um objetivo obrigatório de 30–50 páginas. A versão longa pode existir depois. O propósito é tornar pergunta, resultados fortes, fragilidades e próxima experiência rapidamente compreensíveis, não atingir uma contagem.

### G — Campanhas futuras e automação

Usar a identidade da campanha futura que realmente existir; não assumir que C3 ainda não começou. Criar o esqueleto no freeze de protocolo, acompanhar estados e fechar o relatório posteriormente. CI de documentação separada só depois de template e fontes estarem estáveis; nunca adicionar TeX ao runtime de inferência ou à CI rápida sem necessidade.

## 13. Instrução operacional para entregar ao Codex

> Implementa esta especificação no repositório Tesy, começando por A–D e depois E quando as fontes originais estiverem disponíveis. Trata este documento como proposta de implementação, não como evidência experimental nova. Lê o contrato aplicável e o índice de evidência. Usa o SHA C2 explícito; não assumes que `main` contém a campanha. Mantém todo o sistema em `docs/research-reports/`, salvo uma alteração mínima e justificada a ignore/ligação na documentação. Não alteres resultados, protocolos, thresholds, workloads, código de inferência nem classificações históricas.
>
> Faz apenas as verificações Git necessárias para identificar a árvore e preservar trabalho existente. Trabalha numa branch dedicada e usa commits locais intencionais; não faças push, PR, merge, force-push, reset destrutivo ou publicação remota. Não descarregues modelos, não executes benchmarks e não alteres instalações partilhadas. Usa ferramentas documentais já disponíveis ou uma instalação isolada e explicitamente registada; não introduzas Docker sem ADR.
>
> Implementa primeiro o mapa de autoridade, unidades e estados, depois o template. Extrai métricas estruturadas por seletores explícitos, verifica hashes sobre bytes originais e mantém narrativas/limitações com fontes. Não copies os números ilustrativos do anexo para figuras sem confirmar contexto e comparabilidade. Um científico BLOCKED tem de continuar BLOCKED no PDF.
>
> Produz o piloto C2 completo, executa testes adversariais documentais, compila e revê o PDF. Só declara builds ou testes efetuados quando houver resultado. Se os dados brutos não estiverem acessíveis, assinala isso sem impedir injustificadamente a documentação dos resultados publicados. Se faltar uma fonte obrigatória, bloqueia os claims dependentes, não os inventes.
>
> Não termines apenas com o esqueleto visual enquanto A–D forem executáveis. Entrega fontes, PDF quando compilável, locks, auditoria, comandos efetivamente executados e lista precisa de limites. Não comeces novas experiências para transformar falhas em sucessos. Depois testa generalização em C1 sem criar uma segunda classe. O dossier e a CI são etapas posteriores, não pretextos para atrasar o primeiro relatório auditável.

## 14. Definição final de pronto

O primeiro incremento fica pronto quando houver: classe genérica; estrutura fixa; fonte documental congelada; mapeamento de todos os claims materiais do piloto; números derivados; estados negativos e indisponibilidades preservados; PDF revisto; evidência de execução dos testes documentais; política de versões/correções; e instruções de nova campanha que não dependam da memória desta conversa.

Não exigir correção numérica do runtime como condição para publicar um relatório que precisamente documenta a falta dessa validação. Exigir honestidade documental, rastreabilidade e uma fronteira clara entre observação e conclusão.
