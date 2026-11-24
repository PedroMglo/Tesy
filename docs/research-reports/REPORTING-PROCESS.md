# Documentação contínua do Scale Lab

O agente que executa campanhas publica protocolos, resultados, manifests e o fecho em `research/` e `results/`. A redação, os gráficos, o LaTeX, a auditoria de claims e as versões PDF são responsabilidade do assistente documental. O agente experimental não precisa de escrever relatórios académicos.

Uma campanha com `research/CN-FINAL-YYYYMMDD.md` é **fechada cientificamente**, mas só fica **coberta editorialmente** quando um relatório `CNN-*` está no registo, inclui esse fecho como fonte congelada, valida os bytes atuais, tem derivados e lock atuais, e conserva `audit.json` revisto para a versão exata. O gate `ci/check_campaign_coverage.py` falha se faltar qualquer parte. O gate não afirma que todos os números da prosa são semanticamente corretos nem que a experiência foi reproduzida.

A verificação de evidência corre por pedido na branch escolhida e nos pushes documentais relevantes para `main`. A opção manual `build_pdfs` acrescenta os previews à revisão. Ao fechar uma campanha, o agente experimental publica a evidência. Uma falha `REPORT_REQUIRED_FOR_CNN` identifica o relatório que o assistente documental precisa de preparar para revisão. [Workflow documental](../../.github/workflows/research-reports.yml)

Todo o relatório LaTeX registado entra na publicação contínua quando a metadata e a auditoria passam a `REVIEWED`. O preflight manual verifica os bytes dos PDFs de release na revisão escolhida. Depois do merge na `main`, cria automaticamente uma tag e uma release para cada versão nova. Alterar os inputs de um relatório publicado exige nova versão e nova auditoria. [Publicação e verificação dos ficheiros](README.md)

O bloqueio de merge pelo GitHub depende de o job `evidence` estar configurado como **required status check** na proteção da `main`. A revisão humana aprova a interpretação e o layout.

Estado em 27 setembro 2026: C2 e C3 têm relatórios revistos e o gate passa na branch documental. C03 v1.0.0 tem PDF, hash e auditoria de seis páginas. D00 v1.0.0 conserva o corte histórico R00/C1/C2; a síntese corrente de C3 está em C03 e `CURRENT-LAB.md`. Uma verificação recorrente acompanha futuras atualizações e cria/atualiza trabalho documental, sem executar modelos nem fazer merge.

## Literatura externa e imutabilidade

A literatura científica é uma autoridade contextual separada da evidência experimental Tesy. `\\cite{...}` sustenta contexto, prior art e claim boundaries; `\\evidence{...}` aponta para fontes internas congeladas que sustentam resultados do Tesy. Não usar um artigo externo para validar números de campanha.

Não editar `shared/bibliography.bib` para acrescentar referências a relatórios já publicados: o adapter v1 inclui `shared/**` no `inputs_sha256`, pelo que isso alteraria retroativamente a identidade das releases v1.0.0. Relatórios novos usam `sections/bibliography.bib`, que é versionado dentro do próprio relatório. Uma futura mudança global desta regra exige nova versão explícita do adapter e migração deliberada, nunca mutação silenciosa.
