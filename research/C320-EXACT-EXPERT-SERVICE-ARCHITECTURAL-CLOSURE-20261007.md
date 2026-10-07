# C320 — Fecho do serviço exato de experts

**CLOSED_SCOPED_ARCHITECTURAL_NEGATIVES_NO_PROMOTION.** Os desenhos admitidos de política lógica, transporte lossless e antecipação foram discriminados. Nenhum passou o gate global ou deixou dois sobreviventes complementares para composição. Não há novo preset entregue. **R0 `slots40-persistent` continua como opt-in operacional; M3 parcial, M4 NOT_MET.**

O fecho resulta da evidência e da falta de fundamento para os próximos investimentos admitidos. O orçamento não foi esgotado. Não houve push, PR, alteração de main, default ou serviço habitual.

## Resultados por módulo

Ganhos positivos significam menor duração. Cada percentagem temporal é a mediana das percentagens de dois pares novos; não se somam fases ou módulos.

|Módulo|Intervenção e âmbito|Resultado|Decisão|
|---|---|---|---|
|A, C286|LOGICAL_ROUTE_V1 em E, trabalho fornecido 153+32|Total nominal −5,83%; código +1,53%; decode nominal −17,10%|NO_GO válido; sem mais tuning de hotness|
|B, C293|Componentes originais contíguos por expert, worker nativo e perfil R0|Total nominal +7,47%; código +6,05%; decode +8,45%/+5,16%|Ganhos delimitados de custo, abaixo dos gates global/fase; não promovido|
|C, C309|Gate aproximado duas layers CPU antes, arena separada de 128 MiB, quatro workers reais|Total −15,47%/−8,62%|NO_GO válido|
|C, C318|Uma revisão affine treinada; mesmo horizonte, top4, serviço e target|Total −1,86%/−4,01%; decode −3,18%/−3,69%|NO_GO válido, sem sobrevivente de fase|
|B, C319|Zstd 1.5.7, level1, 64 experts congelados, 384 componentes canónicos|Pesos alinhados poupam 4,46% CPU/4,32% GPU; reconstrução+cópia ≈2,3 ms/componente|Cenário condicionado mais favorável: 8,90%, abaixo do gate de 20%; codec integrado NOT_RUN|
|D|Envelope generoso da parcela atual elegível de prefill GPU|≤4,96% nominal/3,14% código, sob as condições observadas|Operador GPU NOT_RUN: não chega ao gate de investimento de 15%|
|E|Composição, utilidade, confirmação e endpoint de sobreviventes|NOT_RUN_NO_ADMITTED_SURVIVOR|Sem nova qualificação de produto|

C286/C293/C309/C318 medem **trabalho fornecido**, não respostas funcionais livres nem throughput de tokens confirmados. Inputs, todos os braços, tempos absolutos, pares, estados iniciais/finais e 33 logits completos estão preservados nos compactos e raw das famílias. Não houve exclusão de braços lentos, reutilização de pares antigos, subtração de overhead ou alteração dos thresholds. [Mapa dos módulos](../results/c320-exact-expert-service-closure-20261007/modules.json).

## Descobertas e limites causais

**SOURCE_AUDITED:** o relógio de calls da política antiga depende da agenda física. LOGICAL_ROUTE_V1 separa os eventos de routing dos consumidores em waves. Isso altera a política de residência, não os kernels; C286 não demonstrou benefício suficiente nem que o relógio antigo fosse a causa exclusiva da regressão R2 anterior.

O serviço contíguo melhorou cerca de 24,56% no microprobe, mas apenas 6–7% no custo integrado. Estes valores não são intercambiáveis. O store conserva os seis componentes e os valores MXFP4 originais.

Na antecipação, um consumidor primário pode bloquear enquanto outro worker termina o read especulativo; a prioridade de demanda não preempta reads já iniciados. O predictor aprendido reduziu reads inúteis descritivamente, mas não ganhou tempo em C318. O cenário heldout C315 de 12,38%/14,87% continua **ESTIMADO**: não transferiu para uma melhoria física. Nenhuma soma de waits ou reads inúteis é ganho crítico diretamente removível.

C319 reconstruiu exatamente todos os componentes. Biases comprimem melhor, mas já estão residentes e não dão poupança por carga. Separar escalas e nibbles dá 8,08%/7,82% de poupança na amostra antes de padding; mesmo concedendo o melhor componente e reconstrução gratuita, o cenário chega apenas a 12,44%. Estes são envelopes **condicionados** à amostra e ao serviço proporcional aos bytes, não limites físicos universais. Outros codecs, experts não amostrados e alterações de cache/contenda continuam **DESCONHECIDOS**. Não há fundamento observado para construir um codec/runtime adicional ou um motor assíncrono sem causa específica.

## Correctness, identidade e falhas

O target continua GPT-OSS120B MXFP4 GGUF original, SHA `582bd40f…`, routing/top-k/pesos autoritativos, medium, ctx8192, P12/slots40/ub32 e placement do controlo. Não houve fine-tuning, requantização ou mudança de plano numérico nos contrastes R0 de transporte/predição. Todos os 33 logits completos e argmax nativos selecionados de C318 coincidem bitwise com o gold R0. As qualificações anteriores verificaram bytes no consumidor, expert lógico, slot e generation pelo witness C211.

A tolerância gamma257 do operador **auxiliar** affine não é tolerância para drift do target. O fit usa oito conversas de treino, 1.024 linhas por layer; não usa desenvolvimento/holdout. As referências originais só foram reutilizadas nas fronteiras intactas. Não se herda qualidade universal, atenção/KV8K ou sampling estocástico.

Falhas preservadas: C284 configuração CPU-skip; C288 charge/cap; C291 hash da policy; C296 fixture curta para observação; C297 alias dos scores verdadeiros; C300 model-ID; C301 envelope; C303 deadline de preparação e pedidos NOT_RUN; C305 preparação de inventário/fixture; C308 flag presente com valor0; C312 checkpoint dirty; C313 contrato de inventário ausente; C316 fixture ausente no preparador. Reparos receberam identidades novas e não reclassificam negativos anteriores. C317 nominal fica diagnóstico com overhead de decode 3,26%; C318 usa trace-OFF.

[Índice de identidades](../results/c320-exact-expert-service-closure-20261007/identity-index.json): source, patches, protocolos, measurement HEADs, builds, libraries e receitas persistentes. Worktrees privadas C284/C291/C294/C305 limpas. Os modelos, pesos auxiliares, builds e packs ficam locais; código e evidência compacta ficam em Git.

## Recursos, ledger e cleanup

Inventários próprios de 60s, freshness, AC/performance, sensores, mappings, STREAMING e swap0 foram mantidos. C318: cap comum20GiB, stop19,5GiB; peak do scope familiar16.426.545.152B, GPU total6889MiB, Tctl95,375°C, GPU63°C, NVMe57,85°C. O warning de CPU não exclui um braço válido. Não houve resource stop/OOM/swap do workload. Peak familiar não é pico exclusivo de cada braço; RSS e file não são somados. Clocks/energia não qualificados permanecem UNKNOWN.

C319: cap4GiB, peak cgroup112.300.032B, GPU23MiB; bytes canónicos via O_DIRECT, sem fallback buffered. Nenhuma contagem lógica é rotulada como tráfego físico NVMe.

[Ledger final](../results/c320-exact-expert-service-closure-20261007/ledger-final.json) separa wall ativo, envelopes físicos, treino, preparação e diagnóstico. Intervalos aninhados contam uma vez. O índice completo dos raw fica local com hash/referência compacta: [manifesto](../results/c320-exact-expert-service-closure-20261007/raw-index.json). Hashes reutilizados são identificados; não se afirma novo scan integral de raw/modelo/pack. Ordinary derived ≈723,65MB; packs integral+amostra ≈61,94GB na rubrica separada. Nenhuma evidência foi apagada. Saldos e reserva encerram sem transitar.

Cleanup live: scopes próprios inativos, nenhum modelo na GPU, nenhuma porta própria de inferência; daemon habitual ollama ativo e intocado. Identidade atual do R0 persistente foi revalidada, sem nova inferência. C281 mantém a cobertura do seu ciclo real de dois pedidos com reuse. Não se anuncia uma nova sessão qualificada.

## Caminho utilizável e próximo discriminante

Usar [a invocação explícita e limites de C281](C281-PERSISTENT-R0-RESTORATION-RESULT-20261005.md):

```sh
python tools/c143_slots40_optin.py prepare --profile slots40-persistent --cap-bytes 21474836480 --root <novo-root> --port <porta-livre> --duration-s 600
```

Seguem command/start/health/pedidos/stop. A admissão é live; não há fallback para runtime desaparecido de /tmp, auto-rebuild, troca de KV/perfil ou alteração do serviço habitual. Novas preparations capturam o hash atual do monitor. Não foi lançado outro smoke R0 nesta época.

**Único próximo discriminante, NOT_RUN:** antes de um novo desenho, limitar por replay dos journals existentes uma completion do consumidor primário que não bloqueie outro worker, mantendo quatro workers, pins/generation, cópia, prioridade e cancelamento. Medir/limitar também coordenação e contenda. A ocupação dupla observada fornece a causa source; não prova speedup. Isto exige proposta futura, não abre mais física nesta época.

**LOCAL_ONLY.** Fecho LOCAL_ONLY C282 e push posterior autorizado continuam preservados. Base `5aec3bb`; ref local observada de `origin/main` `7a7d3dc`. Commit de análise e seal são separados para evitar hashes circulares.
