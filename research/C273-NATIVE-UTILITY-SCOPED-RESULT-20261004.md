# C273 — resultado útil limitado, sem promoção geral

MEDIDO_NO_TARGET; measurement HEAD `9c0c25a`, oito processos novos, duas famílias ABBA completas após a alimentação AC ser observada novamente. C272 conserva o seu resource stop, os três braços concluídos e as tarefas não executadas; nenhum tempo dessa família entra nos pares C273. O recibo de execução PASS significa evidência e execução válidas; a decisão científica congelada é `NO_GO_TWO_CLASS_NATIVE_UTILITY_SCREEN`.

## População completa

|classe/ordem|perfil|outputs nativos|finish|resultado|primeiro final s|conclusão s|validado s|
|---|---|---:|---|---|---:|---:|---:|
|c273-1-1-a|A|256|stop|SUCCESS|40.812756|85.618304|87.157544|
|c273-1-2-b|B|256|stop|SUCCESS|37.306696|81.639436|82.697635|
|c273-1-3-b|B|256|stop|SUCCESS|37.410644|82.208883|82.964718|
|c273-1-4-a|A|256|stop|SUCCESS|41.219008|86.453470|87.674951|
|c273-2-1-a|A|768|length|OUTPUT_CAP|NA — sem final|178.153494|NA — sem final|
|c273-2-2-b|B|470|stop|SUCCESS|120.489242|128.837630|129.870353|
|c273-2-3-b|B|470|stop|SUCCESS|111.463776|119.187063|120.268667|
|c273-2-4-a|A|768|length|OUTPUT_CAP|NA — sem final|174.475473|NA — sem final|

A é R0 C75/slots40/ub32. B é R2: attention/router num span153, FFN em tiles32 e serviço expert-major com ordem de último uso já qualificada. Medium, ctx8192, pesos/top-k originais, data2026-09-30, temp0/seed42, cap768/deadline360s. Código2105 IDs = prefix1952 +153; planeamento2154 =2001 +153. São inputs warm153 construídos com transcript fornecido idêntico: não são o nominal1532197/cache2044 histórico nem cache reuse de servidor. Os novos outputs não alimentam outro prompt.

## Pares e gates imutáveis

|métrica código|A1/B2 %|A4/B3 %|mediana emparelhada %|
|---|---:|---:|---:|
|first_final_s|8.590599|9.239338|8.914968|
|cold_first_final_s|1.568909|4.059571|2.814240|
|completion_s|4.647218|4.909679|4.778448|
|validated_s|5.117065|5.372382|5.244724|
|prefix_preparation_s|-3.230786|0.482571|-1.374107|
|cold_prefill_s|2.154506|5.397172|3.775839|
|incremental_prefill_s|22.492367|23.665118|23.078743|
|decode_seconds_per_native_output|0.605780|0.630205|0.617993|

Código: `GO_CLASS_UTILITY_SCREEN`, first-final mediano +8,914968%, ambos os pares positivos; proteções medianas >=−5%. Os quatro finais passam o verificador isolado; os 256 IDs nativos, incluindo EOG, são iguais em cada par. Há255 forwards n1; outputs não são forward calls. A redução até resultado validado é +5,244724%, distinta da métrica primária first-final.

Planeamento: A atinge length768 sem conteúdo final nos dois pares; B termina naturalmente com470 outputs e o JSON correto nos dois pares. A presença de uma solução no reasoning de A não constitui final. Sucesso observado A0/2, B2/2: vantagem funcional sob orçamento. First-final/tempo validado de A e os respetivos ganhos são NA, nunca zero. Não se calcula um rácio de latência entre conclusão truncada e resposta correta. Outros tempos medidos continuam na população e no compacto; os outputs mais longos não são eliminados.

O gate exige benefício de latência nas duas classes e ambos os braços corretos para esse contraste. Não passou. `4K`, `CONFIRMATION` e `QUALIFICATION` ficam `NOT_RUN_TWO_CLASS_SCREEN_GATE`; os holdouts C236 não foram abertos. Não aumentar cap, mudar prompt nem reunir C272/C273 para promoção. Este resultado não refuta universalmente expert reuse: conserva o ganho de código e a vantagem funcional de planeamento, sem confirmação geral.

## Clocks, recursos e limites

First-final começa no envio real do call incremental e inclui reasoning. Preparação do prefixo, prefill e decode têm intervalos definidos; first-final não é somado a prefill. Tempo validado usa validator-end monotónico menos request-start; inclui o intervalo observado após conclusão/cleanup/supervisor. O validador e esse intervalo são guardados separadamente. Decode/output é uma métrica nativa descritiva, incluindo EOG no denominador; não é igualdade de compute nem o contador de servidor C75. First-reasoning, mensagens/reasoning completos, IDs oficiais, native output IDs e todos os receipts estão no raw/compact.

Cap comum20GiB, high=max, swap0, guards existentes e inventário60s/freshness por braço. Máximos observados: Tctl95,5°C (warning95, não stop100); GPU67°C/6972MiB; NVMe62,85°C; memory.current16204521472B. memory.peak16225808384B é acumulado do scope familiar, não pico exclusivo de cada filho. Eventos high/max/OOM/oom_kill zero, swap dos scopes zero, nenhum resource stop C273. DIO: dois FDs do modelo diretos e nenhum buffered. Optional clocks/energia não disponíveis de modo qualificado: UNKNOWN, sem claim energético. Gerações de carga CPU/GPU no compacto são contagens lógicas, não bytes físicos NVMe.

Envelope físico medido1929,666438815s; raw preservado16620649B no manifesto. Cleanup observado: scope inactive/MainPID0, GPU13MiB, nenhum processo compute, AC/performance; serviço Ollama e bridge habituais apenas observados. O custo final de fecho/cleanup é reconciliado em C274.

Identidade, build e hashes congelados em protocol.json e file manifests; libraries numéricas C270 intactas, common/parser identificado separadamente. C270 cobre selected bitwise R2 + neutrality e C266 cobre referências independentes de shapes novos. R2 não herda full8K, quality geral, equivalência bitwise R0 ou sampling estocástico. Sem launcher C143 exercitado, preset novo, default, M3 completo ou M4.

Evidência: `results/c273-layer-utility-ac-restored-20261004/{protocol.json,compact.json,paired-analysis.json,family-receipt.json,raw-manifest.json}`. LOCAL_ONLY; nenhuma publicação autorizada nesta época.
