# Documentação contínua do Scale Lab

O agente que executa campanhas publica protocolos, resultados, manifests e o fecho em `research/` e `results/`. A redação, os gráficos, o LaTeX, a auditoria de claims e as versões PDF são responsabilidade do assistente documental. O agente experimental não precisa de escrever relatórios académicos.

Uma campanha com `research/CN-FINAL-YYYYMMDD.md` é **fechada cientificamente**, mas só fica **coberta editorialmente** quando um relatório `CNN-*` está no registo, inclui esse fecho como fonte congelada, valida os bytes atuais, tem derivados e lock atuais, e conserva `audit.json` revisto para a versão exata. O gate `ci/check_campaign_coverage.py` falha se faltar qualquer parte. O gate não afirma que todos os números da prosa são semanticamente corretos nem que a experiência foi reproduzida.

O workflow corre em todos os PRs e nos pushes para branches de campanha. Ao fechar uma campanha, o agente experimental pode parar depois de publicar a evidência; uma falha `REPORT_REQUIRED_FOR_CNN` é o sinal para o assistente documental preparar um PR separado. A revisão/merge da documentação segue a branch de laboratório correspondente e mantém versões anteriores imutáveis. Não se altera o estado científico para satisfazer o gate.

Para o bloqueio ser efetivo no merge, o proprietário do repositório deve configurar o job `evidence` como **required status check** nas branches de campanha protegidas. Sem essa regra, a CI deteta o atraso mas o GitHub pode permitir merge apesar do FAIL. Pushes diretos para branches sem proteção também não ficam bloqueados. A revisão humana continua necessária para aprovar interpretação e layout.

Estado em 27 setembro 2026: C2 está coberta; C3 tem o fecho publicado, mas ainda não tem relatório PDF revisto e registado. O gate falha deliberadamente para C3 até esse trabalho estar concluído. Uma verificação recorrente acompanha futuras atualizações e cria/atualiza trabalho documental, sem executar modelos nem fazer merge.
