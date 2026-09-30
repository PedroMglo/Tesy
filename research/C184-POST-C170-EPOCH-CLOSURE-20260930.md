# C184 — fecho após C170: referência nativa resolvida, prefixo bloqueado

## Decisão

**MMAP_REFERENCE_NUMERIC_QUALIFIED_SELECTED_SCOPE; PREFIX_NOT_DEMONSTRATED; PERFORMANCE_NOT_RUN_PREFIX_GATE.** Fecho por gate, com saldo. Conserva-se o streaming como caminho operacional já qualificado; não existe comparação nova Tesy/mmap que demonstre superioridade causal nem NO_GO universal de mmap.

A questão central da layer24 foi resolvida no conjunto testado. A referência anterior não seguia o plano nativo: experts/router CPU e redução CUDA fundida. A referência independente com esse plano recuperou todos os bits, sem tolerância nova. C169 continua FAIL histórico.

## Plano e correctness

Base7108d7ba21b519d10df1841ffcef3a9b9addbf13; branch `campaign/120b-post-c154-residency-20260930T094754Z`. Upstream8019dc563b1ecbae6b161a70c3a1359f1b206c1e, worktree privada d12811df4e9f37cefd7ad4b5405b9e0825ea4fe5, patch loader bc57a67d571c83ccf3c4a4268b5cb0d6bc071ea3daf78c6f4ac99ad9bb3333bb. Modelo/hash originais inalterados; nenhum download ou requantização.

C172 fez graph_reserve/scheduler/optimizer no_alloc, sem weights/forward, e distinguiu storage, execução, copies e fusão. Routers/tails CPU0–23; routerCPU/tailCUDA24; routerCUDA/tailCUDA25–35; experts/bias/SWIGLU sempreCPU. A localização CUDA_Host/CPU_Mapped não foi usada isoladamente para inferir compute. O addendum source de C184 resolve o router F32: MMVF n1; cuBLAS/CUBLAS_COMPUTE_32F n32, porque MMVF exige<=3 e MMF rejeita>16. Ordem interna do vendor GEMM permanece UNKNOWN.

C173/C174 conservaram falhas do fixture sintético (Q8_0 scale rounding e CPU-last scheduler), corrigidas causalmente antes de weights. C175 passou MXFP4/F16 controles conhecidos e reduçãoCUDA bitwise contra std::fma independente; CPU separado divergiu, controlo negativo. Não são falhas numéricas do modelo.

C179 passou layer24 nos cinco pontos C166; C180 passou25–35 e regressãoCPU0. Revalidaram-se por hash os115 rows CPU1–23 de C169. Resultado:180 rows canónicas únicas, routing IDs/weights/FFN bitwise e finitos. Cinco full logits e neutralidade NONE/STATE/VERIFY vêm da evidência C166 revalidada. A referência lê pesos/biases canónicos e calcula independentemente, preserva outputs/lifetime e verifica assignment do scheduler antes de compute.

**Limite:** native32+4 e ativações FFN capturadas; não referência independente de toda atenção/KV,189+32,warm153,sessão ou7936. Nenhum bitwise cross-profile C75/upstream é anunciado.

## Harness, tentativas e prefixo

C176/C177 falharam antes de weights por SHA do ficheiro policy versus digest do objeto, e schema de inventory versus runtime. C178 recolheu inventário válido e executou apenas sleep, rejeitado pelo guard de mappings não vazios. C179 manteve o guard e passou smoke GGML-linked; expected ldd passou a incluir as dependências GGML externas efectivamente ligadas, com hashes. Nenhuma instalação partilhada foi modificada.

C181 congelou Harmony/data2026-09-30/medium usando renderer/tokenizer nativos, vocab_only sem weights. Arrays e API têm **78 IDs**, não73 como a prosa/name C182 indicou; errata C183 preserva originais. C182 smokeHTTP passou o verdadeiro inventário60s→Popen→monitor→receipt antes de weights.

O primeiro pedido natural respondeu AB, stop normal,53 output tokens. Mas demorou292,4069575s, ultrapassando os240s congelados. O HTTP timeout só limitava inatividade da socket; o runner permitiu ultrapassar o prazo e iniciar o segundo pedido. A run foi parada por PID/start_ticks/exe/cgroup verificados; o segundo pedido não completou. C182 fica FAIL_PROTOCOL_REQUEST_WALL_DEADLINE, não FAIL numérico/térmico nem prova de KV reuse quebrado.

C183 corrigiu prospectivamente o watchdog de tempo total e a verificação no completion. Vinte testes dirigidos passaram, incluindo child/monitor/receipt reais com sensores/transport mocked, progresso de transporte que excede o prazo, classes FILE_PAGING/STREAMING, negativas prelaunch e prefixo. Suite integral NOT_RUN. Não se aumentou timeout, nem se repetiu física para tentar converter a observação em PASS. O gate de prefixo completo permanece NOT_DEMONSTRATED e bloqueia performance/pares.

### Diagnóstico C182 — não benchmark aceite

| Medida do primeiro pedido | Observado |
|---|---:|
| Prompt oficial / output |78 /53 tokens|
| Load/readiness |15,5389s|
| Prefill |138,592855s|
| Decode reportado |153,8096s;0,33808tok/s|
| Primeiro reasoning/text |149,684117s|
| Primeiro conteúdo final |290,924252s|
| Pedido completo |292,406958s|

Tempos preservados como MEDIDO_DIAGNOSTICO_PROTOCOL_FAILED. Primeiro-final inclui tempo anterior, não se soma ao prefill.53 tokens reportados não provam53 forwards. Não existe warm incremental concluído, par de controlo ou speedup. Page ownership UNKNOWN/NOT_EQUAL_MEMORY_CONTROLLED; read_bytes/faults não viram tráfego físico NVMe.

FILE_PAGING/E20: pico cgroup observado20942036992B, GPU1220MiB, CPU64,25°C, GPU53°C, NVMe52,85°C, PSI global máximo5,73; zero swap e zero novos OOM/oom_kill. Reclaim/high observado é regime, não avaria. Isto não identifica que parcela da latência é CPU compute, refault/read, copies ou waits críticos.

## Dois eixos e próximo discriminante

- **Decode:** C142slots44 mantém~5,236tok/s; mmap curto apenas diagnóstico~0,338, sem comparação igual-trabalho. Causa exclusiva nativeCPU/paging UNKNOWN.
- **Prefill:** C142warm~10,33s; C182prompt78~138,59s diagnostic, não warm153/cold512. Sem crossover quantitativo entre workloads.
- **First-final:** C142~19,31s; C182~290,92s diagnostic. Melhorar apenas decode não demonstra<=10s.

Não se inicia performance com prefixo incompleto. Para retomar mmap, um novo discriminante deve separar custo nativeCPU-MoE e paging/reclaim sob trabalho fixo, mantendo uma janela operacional congelada e o watchdog corrigido. Não basta repetir com timeout maior ou aquecer fora do budget. A referência deixa de ser o blocker neste scope; scheduling/page state e latência funcional são a próxima questão. C164CPU52/GPU44 permanece POLICY_NO_GO_TESTED_SCOPE; não houve política nova/freshholdouts e RESIDENCY_FURTHER_PHYSICAL=NOT_RUN_NO_NEW_DISCRIMINANT.

## Utilidade e entrega

Slots40 conserva opt-in/SESSION_PROFILE_IMPROVED_M4_NOT_MET, qualidade12/12,holdout8/8,C13319/20 e retrieval7936/85 nos âmbitos anteriores. C143 com pesos permanece NOT_RUN. Slots44 conserva C140/C142, não herda qualidade/sessão/8K. M3PARTIAL; M4NOT_MET. Nenhum default, serviço, main ou target foi alterado.

## Época, integridade e Git

Nova epoch `post-c170-native-ffn-reference-and-mmap-20260930T145047Z`, início2026-09-30T14:50:47.103193Z, tetos6hwall/2hlive/2GiBraw,900sfecho. C170 permaneceu fechado, saldo não transitou. Ledger append-only inclui envelopes físicos completos e falhas; inventários/server/reference não são somados novamente aos envelopes. Request-active/readiness são publicados à parte quando observáveis; compile/análise/esperas não foram integralmente cronometradas, UNKNOWN como repartição do wall restante.

Orçamento final e envelopes em `results/c184-post-c170-closure-20260930T1612Z/final-budget.json` e `budget-breakdown.json`. Raw novo físico em roots monitorizadas, manifests hash/tamanho revalidados. Outputs compactos e testes ficam Git; weights/builds/raw pesados permanecem locais. Sources C182 são revalidados pelo blob do measurement commit, pois C183 foi um reparo prospectivo.

Sem processos de modelo visíveis próprios; scope C182inactive/dead; GPU12MiB e MemAvailable26141233152B no check final. Page cache continua reclamável/ownership UNKNOWN, nenhuma limpeza global. Remoto7108d7ba21b519d10df1841ffcef3a9b9addbf13 e main7a7d3dcbd1ff8e594ac57459c3db06306083c3ca confirmados read-only. Novos commits locais apenas, sem push/PR/merge. Checkpoint pronto para auditoria pelo owner.
