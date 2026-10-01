# Documentação contínua do Scale Lab

O agente que executa campanhas publica protocolos, resultados, manifests e o fecho em `research/` e `results/`. A redação, os gráficos, o LaTeX, a auditoria de claims e as versões PDF são responsabilidade do assistente documental. O agente experimental não precisa de escrever relatórios académicos.

Uma campanha com `research/CN-FINAL-YYYYMMDD.md` é **fechada cientificamente**, mas só fica **coberta editorialmente** quando um relatório `CNN-*` está no registo, inclui esse fecho como fonte congelada, valida os bytes atuais, tem derivados e lock atuais, e conserva `audit.json` revisto para a versão exata. O gate `ci/check_campaign_coverage.py` falha se faltar qualquer parte. O gate não afirma que todos os números da prosa são semanticamente corretos nem que a experiência foi reproduzida.

O workflow corre em todos os PRs e nos pushes para branches de campanha. Ao fechar uma campanha, o agente experimental pode parar depois de publicar a evidência; uma falha `REPORT_REQUIRED_FOR_CNN` é o sinal para o assistente documental preparar um PR separado. A revisão/merge da documentação segue a branch de laboratório correspondente e mantém versões anteriores imutáveis. Não se altera o estado científico para satisfazer o gate.

Todo o relatório LaTeX registado passa a publicação contínua assim que a sua metadata e auditoria são `REVIEWED`; não há lista manual de inscrição, nem ação do agente experimental ou passo de UI do proprietário. A CI faz o preflight dos PDFs de Release no PR. Depois do merge na branch C3, cria automaticamente uma tag e Release separadas para cada versão ainda não publicada. Uma alteração futura aos inputs de qualquer relatório requer nova versão e nova auditoria; a CI publica essa nova versão automaticamente. Uma versão/tag/Release existente é imutável e nunca é substituída.

Para o bloqueio ser efetivo no merge, o proprietário do repositório deve configurar o job `evidence` como **required status check** nas branches de campanha protegidas. Sem essa regra, a CI deteta o atraso mas o GitHub pode permitir merge apesar do FAIL. Pushes diretos para branches sem proteção também não ficam bloqueados. A revisão humana continua necessária para aprovar interpretação e layout.

Estado em 27 setembro 2026: C2 e C3 têm relatórios revistos e o gate passa na branch documental. C03 v1.0.0 tem PDF, hash e auditoria de seis páginas. D00 v1.0.0 conserva o corte histórico R00/C1/C2; a síntese corrente de C3 está em C03 e `CURRENT-LAB.md`. Uma verificação recorrente acompanha futuras atualizações e cria/atualiza trabalho documental, sem executar modelos nem fazer merge.

## Literatura externa e imutabilidade

A literatura científica é uma autoridade contextual separada da evidência experimental Tesy. `\\cite{...}` sustenta contexto, prior art e claim boundaries; `\\evidence{...}` aponta para fontes internas congeladas que sustentam resultados do Tesy. Não usar um artigo externo para validar números de campanha.

Não editar `shared/bibliography.bib` para acrescentar referências a relatórios já publicados: o adapter v1 inclui `shared/**` no `inputs_sha256`, pelo que isso alteraria retroativamente a identidade das releases v1.0.0. Relatórios novos usam `sections/bibliography.bib`, que é versionado dentro do próprio relatório. Uma futura mudança global desta regra exige nova versão explícita do adapter e migração deliberada, nunca mutação silenciosa.
