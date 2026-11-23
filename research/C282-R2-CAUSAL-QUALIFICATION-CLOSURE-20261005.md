# C282 — rejeição causal delimitada; R0 persistente restabelecido

**NO_GO_R2_CAUSAL_QUALIFICATION_R0_PERSISTENT_RESTORED.** A família completa C280 não admite T nem E sob os gates congelados. Não houve defeito de correctness/observer que sustente reparar e repetir o resultado válido. A época termina pela decisão, não por falta de budget. R0 voltou a passar pelo C143 real, com seleção explícita persistente. M3 PARTIAL, M4 NOT_MET, NOT_DEFAULT; serviço habitual intacto.

## Autoridade, base e fronteira

Owner entregou a ordem pós-C274/C275, GO_REUSE_CAUSAL_ABLATION_AND_SCOPED_QUALIFICATION. Base remota efetiva `d3fea2574b8c382827c957b4f835b55882d8b575`, novamente fetchada no fecho; main permanece `7a7d3dcbd1ff8e594ac57459c3db06306083c3ca`. Branch local `campaign/120b-r2-causal-qualification-20261005T204839Z`, sem upstream/publicação. PR41 de documentação existente é alheio a esta unidade; nenhum novo PR/stack. C274 LOCAL_ONLY e C275 publicação posterior autorizada permanecem intocados; nenhum saldo antigo transita.

SOURCE_AUDITED: não houve mudança de kernels/grafo/loader/aritmética no backend. Cliente novo chama os modos já implementados C269; server R0 maduro compilado separadamente importa os DLLs numéricos qualificados. Defaults históricos e serviço não foram substituídos. A fronteira isolada é:

```text
R0: atenção/router/FFN no percurso ub32 original
 T: atenção/router153 → FFN32 por tile → decode n1
 E: mesma atenção/router153 → waves de experts autoritativos
                            → FFN32 de todos os tiles consumidores
                            → ordenação last-use já conhecida → decode n1
```

Last-use só muda uniões com mais de32 posições; não se inventa um tratamento em T onde o seu caminho não o invoca. T/E têm o mesmo perfil numérico R2. R0/R2 são perfis cross-shape diferentes, não função next-token integralmente igual. Nenhuma previsão substitui o router, experts/top-k, pesos/biases, KV ou contexto8192.

## Reuso, determinismo e falha preservada

Revalidação local4182 ficheiros/548.731.505B dos raw pertinentes C265–C273; source/build/libs/model stat e três backends limpos. O manifesto anterior liga os pesos GGUF à SHA582bd40f…; stat/dev/inode/size/mtime/ctime não mudaram. **Não** houve novo rehash integral63GB. C265/C266/C270 continuam a sustentar bytes/operadores/shape/device e selected bridge, não universal full8K/stochastic/quality. Não repetir36 referências.

REANÁLISE de MEDIDO_NO_TARGET: os oito raw C273 mantêm inputs/transcripts/caps/parser/sampler iguais. Sequências completas nativas repetem exatamente dentro de cada perfil; código também cross-profile. No planeamento, prefixo comum57 IDs; primeira divergência no índice zero-based57: R0 ID1843=` If`, R2 ID8820=` Also`, antes do cap. Exemplos mínimos, hashes integrais e IDs estão no compacto C276; peças decodificadas vocab-only, sem retokenizar outputs ou fazer forward. Nenhuma atribuição a kernel específico. C271/C273 recalculados conservam decisões históricas; C273 permanece NO_GO_TWO_CLASS_NATIVE_UTILITY_SCREEN, A0/2/B2/2 no planeamento, sem rácio de latência válido de A.

C277 FAIL_PREMODEL, antes de collect/Popen/weights: protocolo omitiu o bloco `start_inventory`. C278 NOT_RUN_PREMODEL_CONTRACT_REPAIR. Causa reproduzida model-free; teste/regressão e novos roots C279/C280, mesmos workloads/gates/caps. Falha anterior imutável. C279 PASS: T/E33 vetores completos finitos bitwise iguais no novo input de código, fora de timings promocionais; hashc71b8b0d… . Measurement HEADb816358. C280 volta a verificar T/E33 vetores iguais e estados iniciais completos iguais nos pares; source/library chain intacta. Isso é cobertura selecionada, não prova universal.

## C280: atribuição causal completa

MEDIDO_NO_TARGET: dois casos congelados (C271 nominal2044+153 e códigoC2731952+153),32 IDs nativos teacher-forced,12 processos novos, ordemR0,T,E,E,T,R0 em cada caso. Prefixo sempre preparado modo0, snapshot/drain antes da janela; sem drain entre prefill/decode. Materialização/finite checks comuns no tempo; escritas/hashes pesados fora. Continuação fornecida não é tokens gerados/confirmados de produto. Todos os12 braços measurement/resource/identity válidos; nenhuma exclusão/substituição.

Ganho100×(A−B)/A por par, depois mediana; valores individuais/absolutos em `results/c280-r2-three-way-causal-cost-20261005/paired-analysis.json`.

|Caso|Contraste|prefill153|decode32|total|prefix preparation|
|---|---|---:|---:|---:|---:|
|nominal|R0→T|+3,73644%|−2,46898%|+0,69199%|−2,21714%|
|nominal|R0→E|+13,12701%|**−10,70339%**|+1,44423%|−1,85422%|
|nominal|T→E|+9,75689%|−8,08529%|+0,73935%|+0,35330%|
|código|R0→T|+3,12431%|+0,04133%|+1,85337%|−1,26383%|
|código|R0→E|+22,16408%|+0,63290%|+13,28743%|−1,55089%|
|código|T→E|**+19,65426%**|+0,59167%|**+11,65007%**|−0,31976%|

T não atinge prefill8% em nenhum caso. E falha decode≥−5% no nominal (ambos os pares ~−10,66/−10,75%). A seleção E sobre T também falha total3%/ambos positivos no nominal, pares−1,01256/+2,49126%. Nenhum candidato elegível. Não repetir por variância, não mudar thresholds ou abrir holdouts para escolher outra arquitetura.

O serviço partilhado conserva um benefício material de prefill no código, separado da geometria que por si dá~3%. O decode nominal desfavorável permanece. Estado final/pools/loads são efeitos possíveis da intervenção e foram guardados; não se impôs final igual. Não há decomposição causal exclusiva de wall em I/O/compute ou causa concreta de defeito demonstrada. Menos gerações não é percentagem de tráfego físico NVMe, nem prova de igual-FLOPs.

|Caso|R0 CPU/GPU generations|T CPU/GPU|E CPU/GPU|
|---|---:|---:|---:|
|nominal|1486/638|1479/642|1465/608|
|código|2595/819|2585/840|2290/770|

As contagens repetem nos dois blocos, referentes ao intervalo declarado no cliente. CPU/GPU são tiers lógicos, não leitura física medida. Accounting separado de pools/ativações/reserva de graph/workspace/observer em C276; sampled memory.current e scope-cumulative peak em cada receipt/compact. Picos não simultâneos não são subtraídos como overhead exclusivo. As reservas adicionais de R2 são reais; cap igual não demonstra uso igual. GPU total até6972MiB, CPU warning até95,25°C, NVMe54,85°C nesta família; cgroup preventivo19,5GiB, cap20GiB,swap0, sem OOM/high/max/guard stops. Clocks/energia UNKNOWN; GPU power590,01W pós-run absurdo é UNKNOWN, não zero ou energia.

## Qualidade, utilidade e caminho utilizável

Novo screen/confirm/4K/R2 endpoint: **NOT_RUN_NO_ADMISSIBLE_R2_COST_SURVIVOR**. Holdouts C236 não abertos. Nenhum problema novo sucessivo para procurar PASS. C273 conserva qualidade/ganhos observados naquele código e vantagem funcional na rota; nesta época C280 mede trabalho fornecido e não valida livremente outras tarefas. Não atribuir inteligência à movimentação de bytes nem herdar qualidade do R0 ao R2.

C281: **R0_PERSISTENT_LAUNCHER_TWO_REQUEST_PASS**, ciclo237,101021s, prepare→start→health→dois pedidos com histórico real→stop. Readiness4,041968s, finais48327/48327, finishstop, inputs2043/2197 e segundo cache2044/new153. Mapped libs e GNUOMP unset conferidos; cap20GiB, swap/OOM/high/max0, GPU6860MiB; CPU95,375°C warning válido. OutputIDs HTTP NOT_EXPOSED; native arrays C280 e antigos C273 continuam locais/hashes, sem retokenização. Primeiro final82,64/21,09s e completion83,08/21,37s são descritivos; não demonstram M4. Não se soma prefill a first-final.

Receita/manifesto/paths persistentes e invocação explícita em [C281 resultado](C281-PERSISTENT-R0-RESTORATION-RESULT-20261005.md). Opção `--profile slots40-persistent --cap-bytes 21474836480`. Default CLI histórico slots40 e C35 continuam com os /tmp históricos ausentes; não os anunciar prontos ou transferir KV. O novo path é válido nesta máquina, não portátil. Artefacto desaparecido/mudado falha com diagnóstico, sem auto-rebuild. Nunca alterar serviço/default nesta entrega. R2 permanece somente evidência experimental CAPI/operador, sem preset qualificado.

EAGLE3 B8 encerra como investimento ativo nos scopes C258; nenhuma física/head/download novo. Slots44 conserva âmbitos C140/C142/C203 e negativos posteriores. Native64 N/W históricos, mmap CLOSED_CURRENT_PROFILE_AS_ACTIVE_INVESTMENT e todos os FAIL/NOT_RUN permanecem. M3 PARTIAL/M4 NOT_MET; sem herança full8K/7936/cold512/qualidade universal.

## Ledger, cleanup e revisão recuperável

Nova época C276, sem crédito C274. Ledger append-only; C2801771,334540s, C279298,952001s, C281237,101021s; configure e server build separados. Build32,500679s contabilizado fisicamente conservador. Primeiros helper compile/vocab-only não persistiram endpoints: surcharge físico130s ESTIMADO, sem inventar timestamps/overlap. Preparação pré-abertura600s wall conservadores; todo elapsed da sessão ativa inclui análise/build/espera. Human partition exata UNKNOWN, não tempo subtraído. Request-active/kernel/CPU-segundos não se somam aos envelopes que os contêm. Subtetos repair/integration24hwall/2hlive verificados com o total global como upper bound conservador do subset; permanecem folgados. Detalhe e fecho exatos em ledger-final/closure.json; allowance60s de serialização Git final é estimado, dentro do teto, não física nova.

Raw novo395.131.834B (~0,368GiB),168 ficheiros no manifesto integral novo; nenhum negativo apagado. Artefactos derivados24.870.508B (<12GiB), pesos/builds antigos fora dessa soma, sem novos downloads. Nenhum modelo/build pesado em Git. Raw/hash manifest, source/build/compiler/env/library/model identities e recipes preservados em paths locais persistentes e compactos Git. Não foi CI remota ou repetição da revisão independente.

Cleanup observado: scopes próprios inactive/MainPID0, nenhum compute app/model próprio, GPU12MiB, porta18442 bindable. Serviço Ollama observado inactive, sem qualquer sinal/modificação pelo agente. Estado final/HEAD/tree são verificados após o último commit, sem hash circular no manifesto. Checkpoint pronto para reboot; saldo encerrado não é crédito de nova hipótese.

Unidade futura de revisão: cliente/gate causal `tools/r2_causal_*` e resultados C279/C280; restauração C143/opção explícita/recipe/client/tests e resultado C281; ledger/reconciliação/fecho C276/C282. Patches arquiteturais C262/C269 e campanha histórica permanecem na base, não são integrados num PR monolítico. Sem push/PR/merge/force-push/main autorizado para esta época.
