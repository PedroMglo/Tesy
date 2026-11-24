# Proveniência da unidade

- Objetivo. Decidir se devolver um worker à fila enquanto uma procura exata espera uma leitura já em voo justifica a próxima fixture. Avaliar a geometria de prefill R0 separadamente.
- Base consultada em 2026-11-24. `PedroMglo/Tesy`, `origin/main` confirmado por API GitHub em `293f5b184da9439771cce361cd33fc4068d749f4`, tree `7683d6c07063adef6de232c43ab05d19e98e679d`. Consulta de PRs abertos devolveu zero.
- Worktree original em `main` no mesmo commit, sem diferenças tracked, com artefactos e checkouts locais untracked. Um clone completo independente em pasta temporária usa a branch curta `research/worker-release`. A pesquisa de locks Git encontrou apenas o ficheiro vazio `gh-stack.lock` sem titular reportado por `lslocks`. Preservam-se os worktrees, configurações e artefactos locais.
- R0 operacional `slots40-persistent`, M3 PARTIAL e M4 NOT_MET. Identidades históricas de backend, modelo, workload, build e recursos vêm dos [protocolos C317][c317] e [C318][c318] e dos [blobs congelados][blobs]. O replay é local, só de leitura, sem modelo, sem GPU e sem qualificação física nova.
- O diretório raw da revisão C317 foi localizado num checkout histórico local. Só os pares `events.tsv` e `staging.json` dos quatro braços trace-ON entram na análise. O manifesto de C317 fixa os digests e tamanhos. O raw, caminhos absolutos locais e ficheiros de trabalho ficam fora do PR.
- Os resultados executáveis usam diretórios novos com falha se já existirem. O PR publica resumos, critérios e diagnósticos agregados. As baselines e os FAIL históricos continuam na sua proveniência original.

[c317]: ../../results/c317-learned-staging-observer-qualification-20261007/protocol.json
[c318]: ../../results/c318-learned-staging-contemporary-product-cost-20261007/protocol.json
[blobs]: ../post-c320/source-blobs.json

Protocolo congelado às 21:02:56 UTC, SHA-256
`bd6c451bb94d2206fd4e171d9bc3acf80ff347d0da1946270dc5072c73bf0268`.
Os checkouts locais C305 e C281 confirmaram os pins e as árvores, sem
diferenças tracked. No checkout histórico separado há um
`objects/maintenance.lock` vazio sem titular visível. O estudo estático
de prefill usa a releitura do trace histórico C135 pelo SHA-256 já fixado
em C261. Nenhum lock foi removido, trabalho relançado ou backend modificado.

A correção do mutex partiu da cabeça e7a659db do #44 e conferiu os ficheiros pinados da implementação C305. O aditamento conserva o [pré-registo](protocolo-mutex.md), os [resultados da nova projeção](receipts/audit-mutex.json) e o [primeiro recibo](receipts/audit.json). A medição física histórica e a ordem interna dos journals são as mesmas nos dois cálculos.
