# Handoff — reporting v1.0.0

Resultado: sistema documental e quatro relatórios. Os resultados executados, contagens, hashes dos PDFs e ambiente ficam em `validation/` e nos release manifests. Reprodução experimental NOT_RUN; raws NOT_ACCESSED.

Base observada: `7a7d3dcbd1ff8e594ac57459c3db06306083c3ca`. Branch local: `docs/research-reports-20260927`. C1 original: `c67529e290844bb3d9033615072d5878014a46bc`; C2: `81531d9dc33caddbbf07928106de47cfe2a6d42a`.

## Integração seguinte

Num clone completo, redescobrir main, branch/HEAD/upstream e worktree; verificar se a pasta já existe. Criar uma branch dedicada da base apropriada e aplicar os patches com `git am`. Se main avançou, auditar o delta; não fazer force-push nem sobrescrever uma pasta existente com o ZIP. Reexecutar os testes model-free e a verificação dos quatro documentos. O pacote de patches identifica commits/base fora dos ficheiros que identificariam o próprio commit.

Apenas `docs/research-reports/` é acrescentado. Código de inferência, modelos, protocolos, resultados originais, CI existente e as outras árvores ficam inalterados. O object store local é seletivo; não se afirma `git status`/CI de um clone completo.

## PR e CI

Não existe PR remoto desta entrega e não foi ativada CI remota. A stack existente não foi modificada. Na consulta registada durante o trabalho, #25 era o PR aberto mais baixo com base main; é candidato a revisão, não foi certificado mergeável. O endpoint de status devolveu uma lista vazia, o que não prova CI PASS nem ausência de checks. Conversações e checks completos: NOT_AUDITED. Os PRs acima ficaram sem intervenção; #35 aparecia draft na consulta. Antes de qualquer revisão/merge, redescobrir esses estados.

## Limites que permanecem

C2: CORRECTNESS_BLOCKED; C1: SUCCESS só histórico; R00: recorte do ledger, não auditoria exaustiva; dossier: corte26setembro. Sem nova pesquisa de prior art, revisão de orientador, inspeção live do host físico ou reanálise dos raws. A autoria pessoal não foi inventada.

Campanhas futuras usam a identidade real que existir, não C3 por suposição. O esqueleto nasce DRAFT/NOT_RUN. Correções têm novas versões; os PDFs e locks antigos não são reescritos. O dossier fixa as versões dos filhos explicitamente.
