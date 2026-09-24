# Resultado de timing do live MoE handoff — 2026-09-24

## Resultado

**MEDIDO:** a campanha `results/live-moe-handoff-timing-20260924T194737Z/` passou e decidiu `LIVE_MOE_HANDOFF_TIMING_SERIAL_PIVOT`; a execução escolhida é `serial`.

Measurement commit: `be2107ef1e593af29b37fa3465e780ddd6c2c765`.
Measurement tree: `f73e16cd402a78093be09e0953e89b3ad7027133`.
llama.cpp: `4e416ee7308dd6b581796f1a6241276cd5982691`.
Modelo: `gpt-oss-20b-mxfp4.gguf`, 12,109,564,352 bytes, SHA-256 `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`.
Prompt: `benchmarks/prompts/b0-b1-diagnostic.txt`, SHA-256 `431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6`.

Classificação: `MEASURED_LIVE_MOE_HANDOFF_TIMING_DIAGNOSTIC`. Mede apenas a boundary residente de uma rota stock live repetida na layer 0, nas janelas `activation_ready -> output_ready` e `route_ready -> output_ready`. Não mede cache misses, H2D/NVMe de pesos, tráfego físico, prefetch, reinjection, committed-token continuation ou latência production stock ininterrupta.

## Integridade do método

**MEDIDO:** dois processos físicos novos (`h=2`, `h=3`), token `2167`, experts `[1, 13, 17, 21]`, 6 warmup triplets, 81 measured triplets e `inner=1`. Cada modo completou 87 trials, persistiu 81 amostras por janela e passou os 261 `successful_timing_trial_rollbacks`.

O schedule foi 13 ciclos completos das seis permutações e tail `[0, 3, 4]`; cada modo ocorreu exactamente 27/27/27 vezes nas posições ordinais. O Python recomputou estatística e decisão dos raw samples; C++ não decidiu GO/PIVOT/NO_GO.

**MEDIDO:** exactness pré e pós timing passou em ambos os `h`: retorno zero para stock/handoff early-stop, ambos os rollbacks, activation/reference, stock-output/reference e paridade serial/async contra stock e entre si. Mantêm-se relative max `<= 0.005` e cosine `>= 0.9999`.

## Timings e razões medidas

| h | janela | stock median / p95 (ms) | serial median / p95 (ms) | async median / p95 (ms) | serial/stock median / p95 | async/stock median / p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | route-ready | 1.296870 / 1.689678 | 0.953664 / 1.141417 | 0.886949 / 1.172325 | 0.735358 / 0.675523 | 0.683915 / 0.693816 |
| 2 | activation-ready | 1.315675 / 1.729944 | 0.974433 / 1.159541 | 0.908199 / 1.194517 | 0.740634 / 0.670277 | 0.690291 / 0.690495 |
| 3 | route-ready | 1.296058 / 1.724424 | 0.810505 / 0.959825 | 0.654491 / 0.962962 | 0.625362 / 0.556606 | 0.504986 / 0.558425 |
| 3 | activation-ready | 1.314694 / 1.742047 | 0.828409 / 0.982489 | 0.671803 / 0.980305 | 0.630115 / 0.563985 | 0.510996 / 0.562732 |

**MEDIDO:** async bate stock nos quatro critérios nos dois `h`, mas `async_overlap_retained=false` nos dois, pois não retém simultaneamente route median estrita e route p95 não-pior versus serial. Serial bate stock em median e p95 nas duas janelas nos dois `h`; por isso aplica-se a regra pré-registada `LIVE_MOE_HANDOFF_TIMING_SERIAL_PIVOT`.

Os ceilings diagnósticos mínimos para futuro gate serial são activation median 0.341242 ms, activation p95 0.570403 ms, route median 0.343206 ms e route p95 0.548261 ms. São `stock - serial` sob o comparator callback-instrumented, não um bound de production stock.

## Recursos, reparações e limite de claim

**MEDIDO:** `reference_host_check=PASS`, host físico sem virtualização, AMD Ryzen AI 9 HX 370 (24 CPUs lógicas) e RTX 4060 Laptop. No início: driver `615.71.09`, VRAM livre 8,271,167,488 bytes, RAM available 24,082,444,288 bytes e zero processos GPU compute concorrentes. O modelo está em `/home` sobre NVMe. Telemetria: 91 amostras GPU válidas, zero falhas, zero swap de processo, mínimo RAM disponível 23,499,259,904 bytes, pico GPU 922,746,880 bytes, máximo 53 C e 30.76 W.

O bootstrap CUDA/build passou; mixed SHA-256 `f515bbe50d16d9a96994bda7c0207bccb179a3fc2284acf7765df2b84735cf77` e capture SHA-256 `c262798adcfe5771a5aeb0375297ed278c64540a21556d0d262adc3eacc091ee`. Runtime provenance h2/h3 passou para executable, argv e única `libggml-cuda.so`. **DESCONHECIDO/limitado:** `nvcc --version` no doctor foi `NOT_AVAILABLE`; isto não substitui o build CUDA e runtime provenance que passaram.

`results/live-moe-handoff-timing-20260924T194713Z/` está preservado com `FAIL_CAMPAIGN_STAGE`: o sandbox recusou criar o lock em `/run/user/1000` antes de executar o modelo. Não é evidência de timing; a campanha válida usou um root novo.

Foram reparados dois falsos contratos textuais antes da medição: o contrato exactness incluía helpers de timing no slice e contava cinco rollbacks em vez dos dois do executor; o contrato async esperava a guarda antiga e não cobria `live_handoff_timing`. Há regressões e registos em `LIVE-MOE-HANDOFF-TIMING-CONTRACT-REPAIR-20260924.md` e `MODEL-FREE-ASYNC-CAPABILITY-CONTRACT-REPAIR-20260924.md`.

Este resultado não demonstra speedup end-to-end, tráfego físico, cache hit rate ou vantagem de prefetch. Stock tem `cb_eval`, pelo que a folga é diagnóstica nesta boundary. Não foi implementado reinjection, continuation, cache/residência dinâmica ou prefetch.

## Próximo gate autorizado

Se explicitamente autorizado após revisão, o próximo gate usa apenas `serial` e estes ceilings como diagnóstico, exigindo comparação independente same-work de token committed contra stock sem interrupção. Async fica excluído. Não foi implementado trabalho posterior neste PR.
