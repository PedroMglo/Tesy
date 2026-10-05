# C275 — publicação e handoff antes de desligar

Estado: época pós-C235 encerrada em C274, sem inferência ativa. O owner autorizou agora publicar a branch e materializar a continuidade se nenhuma execução restante fosse admitida pela ordem principal. Este registo é manutenção/publicação, não nova campanha, novo budget ou reclassificação de resultados.

## O que está completo e o que falta

|frente|resultado preservado|restante condicionado|
|---|---|---|
|A: verificador/EAGLE3|B8 perfect-assist GO; head real mais lento nas duas classes C258|screen útil2K/4K, confirmação e Q NOT_RUN_DEVELOPMENT_GATE|
|B: reuso expert-major|operador elimina cargas; referência/correctness próprias; custo prefill153 +18,19%, decode protegido; C273 código first-final +8,91%|screen de duas classes não passa; 4K, confirmação e Q NOT_RUN_TWO_CLASS_SCREEN_GATE|
|planeamento C273|B correto2/2, A length768 sem final2/2|latência comparável NA; não inferir rácio nem abrir holdout para selecionar desenho|

A condição para avançar às execuções restantes não está satisfeita. Não surgiu uma causa concreta nova que autorize reparar/repetir a mesma configuração. A ordem admite conservar benefício limitado a uma classe sem promoção geral e sem consumir automaticamente a reserva. Caps, prompts, thresholds e os negativos permanecem. C274 não é reescrito para apagar o fecho LOCAL_ONLY anterior à publicação.

## Checkpoint persistente

- Branch: `campaign/120b-block-verifier-expert-reuse-20261004T105527Z`.
- Base publicada: `8c78f598e446b1b09fb3ba518b77e0d7496bfa47`; fecho local: `dd19be1dac97a5fb536cd0a674790b1348686d07`.
- Decisão e mapa de revisão: [C274](C274-BLOCKS-EXPERT-REUSE-CLOSURE-20261004.md); população útil completa: [C273](C273-NATIVE-UTILITY-SCOPED-RESULT-20261004.md).
- Ledger fechado: `results/c236-post-c235-blocks-expert-reuse-20261004T105527Z/closure.json`; detalhe: `results/c274-post-c235-architectural-closure-20261004/ledger-final.json`.
- Identidades/build recipes: `results/c274-post-c235-architectural-closure-20261004/identity-manifest.json`.
- Índice SHA/tamanho do raw completo: `results/c274-post-c235-architectural-closure-20261004/all-raw-sha256-manifest-index.json`; manifesto integral local no caminho indicado, preservado fora de Git.
- Patches reproduzíveis: `patches/c262-layer-expert-reuse.patch` e `patches/c269-authoritative-last-use-order.patch`, mais recipes pinadas e ferramentas versionadas.
- Backends/builds privados persistem em `backends/c236-block-verifier-c75`, `backends/c262-layer-expert-reuse`, `backends/c269-layer-last-use`; binários/head/fixtures locais persistem sob o build C236 dentro do projeto.
- `results/c275-publication-handoff-20261005/persistent-artifact-check.json` confirma a presença dos artefactos críticos e hashes selecionados, sem forward ou full-model rehash.

Não há dependência de /tmp nos ficheiros críticos do último experimento. O runtime C143 histórico em /tmp já desaparecera antes desta época: não passou a estar restaurado/qualificado por existir um novo build. Slots40 conserva a configuração opt-in histórica; R2 não é preset entregue. Os pesos originais continuam no caminho do modelo declarado no manifesto. Git remoto guarda código, protocolos, resultados compactos e manifestos; raw, pesos e builds continuam locais e devem ser conservados neste disco.

## Depois do arranque seguinte

1. Ler este handoff, C274 e `closure.json`; manter o saldo encerrado. Não executar os protocolos antigos como uma nova run nem repetir os braços para obter PASS.
2. Redescobrir HEAD/upstream/dirty/worktrees/processos e eventual delta remoto. `git status --short`, `git branch -vv`, `git log -5 --oneline`.
3. Revalidar paths/estatísticas do modelo, source/backend HEADs, libraries incluindo libgomp e env seletivo. Rebuild ou mudança de libraries recebe identidade/bridge próprios; não herdar hashes anteriores.
4. Antes de física autorizada, observar de novo host/GPU/RAM/swap/disco/AC/performance/sensores/ancestrais e fazer inventário/guards correntes. O boot/monotónico pode mudar; nenhuma epoch ativa ficou aberta para atravessar o reboot.
5. Para nova promoção B, obter uma decisão prospetiva sobre comparador que termine na segunda classe ou um contrato de utilidade/censura explícito. Não usar o reasoning truncado como final ou calibrar retroativamente cap/prompt. Os holdouts C236 permanecem não observados.

Nenhuma destas leituras autoriza inferência nova depois do fecho. M3 PARTIAL, M4 NOT_MET, default e serviço habitual intactos.

## Shutdown e publicação

Observação live em `shutdown-ready-observation.json`: GPU13MiB, nenhum compute ou processo experimental próprio, apenas slices vazias; Ollama e bridge habituais observados sem sinais. Nenhum endpoint experimental foi aberto pelos clientes CAPI. A lista completa de portas fica apenas no raw local.

Publicação autorizada agora somente para esta branch e checkpoint/handoff; sem PR, main, merge ou force-push. O SHA efetivamente publicado e a igualdade local/remoto são verificados após o push, fora do próprio commit. Dados do projeto são sincronizados no filesystem antes da entrega final. O agente não executa o desligamento do computador.
