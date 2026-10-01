# C208 — portfolio encerrado sem vencedor confirmado

## Decisão

**H1: SCREEN_GO_NOT_CONFIRMED. H2: NUMERIC_BRIDGE_RESOURCE_STOP.** Slots40/ub32 continua o opt-in validado C188, SESSION_PROFILE_IMPROVED_M4_NOT_MET, M3PARTIAL, NOT_DEFAULT. Slots44 mantém C140/C142 e um novo screen de SQL; não recebe qualificação geral, sessão/7936, default ou novo preset. M4NOT_MET.

Base publicada c97484433925cd0664ca27e1b5dcba76b1cb66f3; branch campaign/120b-post-c154-residency-20260930T094754Z, main7a7d3dcbd1ff8e594ac57459c3db06306083c3ca. Fecho histórico C198 LOCAL_ONLY preservado, push posterior do owner reconciliado em C199. Novo trabalho LOCAL_ONLY, sem autorização de push/PR/merge. Measurement S22b476257daa3fb7a740b01ca5bb6604d08d46e3; bridge53d4ca1 e C82be38b, SHAs completos nos recibos. Fecho commit é o HEAD posterior, sem hash circular.

## H1 — screen válido, não confirmação

MEDIDO_NO_TARGET: quatro processos originais C75, ub32, slots40/44/44/40, E20 comum, próprios inventários60s e freshness≤3s no Popen. Todos12 pedidos naturais/funcionais, mesmas mensagens fornecidas e IDs2043/2197/2292; T2cache2044/new153. Novas respostas não alimentam este transcript fixo. Nenhuma afirmação de compute/routing iguais entre perfis.

|Braço|Slots|T2prefill s|T2decode reportado s|T2first-final s|SQLfirst-final s|SQLvalidado s|
|---|---:|---:|---:|---:|---:|---:|
|c203-1-A|40|10.775|7.783|18.259|61.679|76.877|
|c203-2-B|44|10.352|6.712|16.781|59.205|73.865|
|c203-3-B|44|10.387|6.709|16.810|56.266|70.336|
|c203-4-A|40|10.947|7.701|18.340|64.781|80.109|

Ganhos SQL por par3,917803% /12,199019%, mediana8,058411%: GO_SCREEN pelo gate≥8%, ambos positivos. Mediana T2first-final8,217935%, SQLfirst-final8,577230%; todas as proteções medianas≥−5% e individuais≥−15%. Dispersão relevante e margem muito pequena: não converter este screen numa melhoria confirmada. Ganhos calculados por par com denominadorA, nunca ratio de medianas. Reanálise offline reproduziu integralmente os quatro recibos e a decisão.

CPU increment expert copies1321920000B, GPU581644800B, total1903564800B; actual GPU peak6866/7420MiB, abaixo guard7676MiB. Cgroup peaks~15,73/17,05GB. Warning CPU95/95,25°C permitido abaixo100; nenhum OOM/swap/guard. Clocks driver cpufreq e contadores energia core/package foram registados, não somados nem chamados compute/latência. Uma leitura opcional pós-cleanup power590,01W é inválida/UNKNOWN; nova observação11,44W. Não altera dados/gates nem fabrica hardwareFAIL.

## H2 — mecanismo observado, bridge não qualificado

SOURCE_AUDITED: C75 original/OpenMPON, GNU libgomp16.2.1-2.fc44 efectivamente mapeada e SHA637b2ab4eedf3ce72173a9d34a4c41c480082d68662db3f0ef4998117df8f9b2. OMP/GOMP/KMP selectivos congelados, incluindo unset versus0. Não houve recompilação C75. C201 fixture real GGML8threads, callbacks máscara255,64repetições/delay0/50/500/5000µs em ABBA, saídas exactas. REPRODUZIDO_MODEL_FREE: CPU-segundos mediana−97,451087%/−99,268602% nos casos500/5000µs, gate25% passa. Resultados/wake wall no caso0 também preservados. Isto não é ganho de latência120B. [GOMP_SPINCOUNT](https://gcc.gnu.org/onlinedocs/libgomp/GOMP_005fSPINCOUNT.html), [OMP_WAIT_POLICY](https://gcc.gnu.org/onlinedocs/libgomp/OMP_005fWAIT_005fPOLICY.html).

C209 controlo original parou no guard STREAMING E18: current18814455808B≥18790481920B. File charge4572921856B, RSS15938990080B; fd canonical byte witness buffered SOURCE_AUDITED, contribuição para filecharge INFERIDA. Não é tráfego físicoNVMe. Sem OOM/oom_kill/swap; host MemAvailable≥9,327GiB, PSI full≤0,32%. Nenhuma comparação numérica A/B completada; B e S-H2 NOT_RUN. Não elevar cap, mudar política para FILE_PAGING, desactivar bytes/guards ou repetir. C204 draft anterior ao fim dos checks também NOT_RUN, C209 é a única tentativa física bridge.

Stop foi específico à captura: servidor H1 tinha apenas fdO_DIRECT e passou em E20. Scopes terminados, GPU/porta livres, fonte/libs inalteradas; isso permitiu readmission independente C com novos inventários, sem contornar risco global.

## C — controlo não entregou final no holdout

Primeiro braço40 completou naturalmente T1/T2/SQL conhecido, mas o holdout independente consumiu384 outputs reportados em reasoning e terminou length, conteúdo final vazio. IDs2582, cache2293, novos289; prefill37,328603s, decode86,822286s, primeiro reasoning38,218851s, primeiro final NÃO OBSERVADO. Deadline180s não foi atingido; erro é ausência de final/natural completion, não timeout, hardware, corrupção ou SQLite errado.

Resposta completa e reasoning preservados antes do reject. Não executar a SQL esboçada no reasoning, regrade, alongar caps/timeouts ou inferir resultado funcional. Todos os outros cinco braçosC NOT_RUN; ganhos/pairsC NOT_COMPUTABLE, não0. Nenhuma conclusão comparative40/44 no holdout. Qualificação/preset adicionalC207 NOT_RUN_NO_CONFIRMED_WINNER. A capacidade384 falhar no controlo não rejeita a aritmética nem prova impossibilidade de44, mas encerra esta família conforme os gates.

## Harness, identidade e limites

47 testes dirigidos iniciais PASS;14contraprovas capture/gate PASS com raw histórico C48;20 testes adicionais de quatro tasks.messages fixos/holdout-prefix/SQL e clienteC143 PASS. São execuções dirigidas, com algumas suites repetidas, não total de testes únicos nem suite integral. Actual child ownership/proc e libgomp no caminhoC2, sensores/transporte fixtures sem shim de ownership. Contraprovas grader incluem joins duplicados, clientes omitidos, cancelled/NULL, escrita/extensões, recursion bound. Root/inventário/hash/deadline e evidência preservados. Teste detectou token_ids não inicializado em falha precoce; reparo inicializado antes do launch, sem grafo/kernels.

C200 freeze incompleto e C202/C204 drafts durante preparação permanecem NOT_RUN, nenhum inventário/Popen/weights. Não houve recovery de uma tentativa física. C203/C209/C206 únicos modelos desta época. Revalidámos6266 rawC140,52rawC196, capturas e manifestsC127, modelo inode/stat/checksum prévio, binário servidor e cinco backendlibs. Mesmos sources/libs/CMake/compile flags C e C++ originais, sem rebuildC75. Referências36C140/C127 reutilizadas, não repetidas. Native64C191/C192 só preservados, não qualificam H1/H2. C196/C197/C13319/20/C164CPU52GPU44/C170 e mmap fechado ficam intactos.

`profile-identity-manifest.json` mantém toolchain, flags, pins, paths/hashes e receita existente de reconstrução, origem C190. Runtime real em/tmp NÃO tem garantia de sobreviver reboot/limpeza; o manifesto persiste, rebuild exige identidade e bridge próprios. Opt-in original: prepare→command→start→health→HTTP→stop em tools/c143_slots40_optin.py. FallbackC35 apenas --profilec35, novo root, sem troca silenciosa/KV entre perfis. Nenhum serviço/default alterado.

## Próxima observação mínima — apenas proposta

O blocker agora é finalizar naturalmente a tarefa independente no controlo com medium. `next-discriminant.json` propõe, sob nova autoridade, UM canary slots40/ub32 com o mesmo transcript/contexto, output cap768 só para holdout e deadline240s, servidor600s, envelope720s completo; toda preparação≤900s wall. É prospectivo, identity nova, nenhuma alteração desta falha384. Se não entregar SQL final natural e passar as seis fixtures, parar sem retry. Estabelece viabilidade funcional, não speedup/M4. Uma futura confirmaçãoH1 exigirá todos novos pares e contrato íntegro; H2 precisa antes de fonte/capacidade de um witness numérico E18 sem a charge buffered adicional, não implementado aqui.

DECODE: redução S descritiva T2seconds/output13,32% e SQL7,77%; routing/outputs podem diferir. PREFILL: ganhos S cold~2K3,43% e incremental1534,52%, ainda~10s. FIRST-FINAL: T2~16,8–18,3s e SQL~59–65s; fase anterior já incluída. Holdout mostrou289novos37,33s mais reasoning sem final. Nenhum desses âmbitos prova cold512≤30s, prefix4096, full8K/sessão, decode≥6 ou first-final≤10 do contrato M4.

## Budget e cleanup

Epoch post-c198-useful-latency-portfolio-20260930T235456Z; abertura 2026-09-30T23:54:56.200563+00:00. Consumo científico de fecho: live1531.943236s/7200, wall4662.177776s/14400, raw89358218B/2GiB. Reservas180live/600wall não usadas para outra hipótese. Ledger append-only, envelopes aninhados contabilizados uma vez, estimativas sem endpoints não recebem dedup. Builds/model-free são wall, não inferência. Request-active/tempos nativos no phase-accounting separados do servidor/envelope; partição total análise/espera/trabalho humano UNKNOWN, nenhuma pausa nova do owner registada. Saldo restante retirado, nenhuma extensão implícita. Finalisation receipt regista o wall administrativo posterior, sem apagar o fecho.

Cleanup observável: todos os scopes/MainPID próprios inactivos/0, compute processesGPU vazios, porta18367 livre, gráficos residuais12MiB. Nenhum sinal adicional necessário, serviço habitual intacto. Raw2564files com hashes/tamanhos incluindo aborted/length preservados locais, nenhum modelo/build/heavyraw noGit. Compacts, source/testes/ledger e manifests locais prontos a auditar, sem publicação remota.
