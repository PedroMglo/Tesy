# Tempo de publicação de cinco experts CPU0

## R02. NO_GO nesta wave de cinco faltas

Em modo MIN, a redução mediana emparelhada de DIRECT no tempo até à última notificação de publicação foi **3,44% face a STAGED** (5/6 pares positivos) e **3,51% face a DENSE** (6/6). O critério pré-registado exigia uma redução de pelo menos 5% e cinco pares positivos nos dois contrastes, com mediana favorável no retorno ao consumidor. O resultado fecha a promoção desta configuração a uma avaliação de serviço mais ampla com base neste lote. [Protocolo](protocol.md) · [Recibo auditado, seis blocos e 180 gerações](physical-r02/receipt.json) · [Qualificação numérica anterior](../packed_real_layer/README.md)

Cada processo usou as mesmas escolhas de rota do tile CPU0, cinco faltas de residência a partir de 40 slots vazios e quatro workers. STAGED e DIRECT partilham o binário e o layout. O primeiro faz três SET por registo, e o segundo indica o próprio slot como destino de pread. DENSE usa o binário original e três tensores contíguos distintos. O instante final de publicação é o quinto notify após a mudança para RESIDENT sob mutex. A janela exclui o FFN e o resto do pedido. Mantêm-se **M3 PARTIAL e M4 NOT_MET**.

| Bloco | DENSE MIN | STAGED MIN | DIRECT MIN | DENSE DETAIL | STAGED DETAIL | DIRECT DETAIL |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 23,267 | 23,176 | 22,417 | 22,724 | 23,774 | 22,764 |
| 2 | 23,235 | 23,204 | 22,219 | 23,006 | 22,602 | 22,474 |
| 3 | 22,748 | 23,000 | 22,304 | 23,036 | 23,290 | 22,187 |
| 4 | 22,819 | 23,162 | 22,048 | 23,203 | 23,116 | 22,227 |
| 5 | 23,034 | 22,785 | 22,962 | 23,174 | 23,104 | 22,227 |
| 6 | 23,204 | 23,186 | 22,349 | 22,847 | 23,292 | 22,427 |

Cada célula contém ms entre o início da espera do consumidor e a última notificação de publicação. Os ganhos MIN, calculados antes de arredondar, foram +3,28%, +4,24%, +3,02%, +4,81%, -0,78%, +3,61% contra STAGED, e +3,65%, +4,37%, +1,95%, +3,38%, +0,32%, +3,68% contra DENSE. Os ganhos medianos na retoma foram +3,76% e +3,51%, respetivamente. O compacto conserva as seis diferenças e a dispersão mínimo/mediana/máximo de cada janela.

| Layout | Publicação MIN em ms, mín./mediana/máx. | Mediana DETAIL/MIN publicação / externa | Pares a ±15%, publicação / externa | READ worker-ms / união ms | SET worker-ms / união ms | União READ ou SET ms |
|---|---|---:|---:|---:|---:|---:|
| DENSE | 22,748 / 23,119 / 23,267 | 0,998 / 0,997 | 6/6 / 6/6 | 73,479 / 22,344 | 3,657 / 3,590 | 23,011 |
| STAGED | 22,785 / 23,169 / 23,204 | 1,009 / 1,007 | 6/6 / 6/6 | 73,355 / 22,417 | 3,849 / 3,666 | 23,186 |
| DIRECT | 22,048 / 22,327 / 22,962 | 1,006 / 1,006 | 6/6 / 6/6 | 73,482 / 22,318 | 0,000 / 0,000 | 22,318 |

O efeito adicional da instrumentação DETAIL face a MIN passou a neutralidade nos três layouts. Para cada um dos 18 braços DETAIL, o compacto conserva os cinco intervalos READ, os intervalos de cada SET, o worker que publicou a geração e o tempo do último produtor. O total de worker-ms pode exceder a duração de parede. As uniões de READ e SET podem sobrepor-se. As diferenças de parede incluem variação entre leituras e quaisquer custos de coordenação.

O expert 49 foi o último publicado nos 18 braços DETAIL, seis por layout. Para reabrir a hipótese, é precisa uma agenda de serviço em que um custo evitável se torne crítico durante a conversa e que se possa distinguir da variação das leituras.

| Layout | Faltas minor no pré-toque, mín./mediana/máx. (12 processos) | Faltas major | Duração do pré-toque, ms mín./mediana/máx. |
|---|---:|---:|---|
| DENSE | 129 094 / 129 094 / 129 094 | 0 a 0 | 73,459 / 79,159 / 85,756 |
| STAGED | 129 121 / 129 121 / 129 121 | 0 a 0 | 73,898 / 78,926 / 84,883 |
| DIRECT | 129 121 / 129 121 / 129 121 | 0 a 0 | 73,601 / 76,066 / 78,357 |

Os 36 pares de snapshots RUSAGE_SELF anteriores e posteriores à escrita do banco, acompanhados dos deltas minor e major, estão no recibo. O custo de pré-toque está fora dos endpoints de serviço. A família durou 66,819 s, com 61 amostras C118 em 60,182 s. Cgroup de 4 GiB com stop preventivo a 3,5 GiB e pico 647 368 704 B, swap 0 B. A monitorização registou CPU até 57,000 °C, GPU até 43,00 °C, NVMe até 34,85 °C e PSI full avg10 até 0,00%. Zero processos de compute GPU observados.

As 180 chamadas ao pack pediram 2 379 939 840 B, com 2 379 456 000 B de payload lógico. Os 360 SET somaram 1 586 304 000 B. O contador de dispositivo do cgroup, que cobre a família, está no campo `io_stat`. Todos os managers e workers terminaram. Os três layouts leram o pack parcial e executaram apenas a wave de serviço CPU.

Execução em `2188e76e8ebcdb5eab0f96498ac9c8f602db50f5`. O recibo privado da família tem SHA-256 `d468411f1ffcf11e8bd3bc7cf9a44e62b6d1bc695cd476677a8ec06e1a6c4fb5`. Para reproduzir a compactação, usar a árvore do commit observado, o diretório privado original e uma saída exclusiva. O auditor recompõe as 36 linhas e a decisão a partir dos journals nativos antes de comparar com o recibo terminal.

```sh
python3 -I -B compact.py --study "$STUDY_FROZEN" --raw "$RAW_FAMILY" \
  --unit "$SYSTEMD_UNIT" --new-output-dir "$NEW_COMPACT"
```

## R01. FAIL_TELEMETRY

A medição R01 terminou os 36 processos e verificou as 180 entregas dos cinco experts. O programa original guardou `PASS_C291_MEASURED_FIVE_MISS_FAMILY`. A auditoria do protocolo identificou a ausência das faltas de página ocorridas durante o pré-toque de cada processo. O programa nativo guardou o tempo e os bytes tocados; as dez amostras do cgroup cobrem períodos que atravessam diferentes subprocessos. **A decisão económica desta identidade é inadmissível.** Os números seguintes conservam a tentativa original e o resultado mecânico do avaliador. [Protocolo](protocol.md) · [Correção prospetiva](r02.md) · [Recibo R01 com as 36 linhas](physical-r01/receipt.json)

Os seis blocos usaram todas as permutações dos três layouts e alternaram a precedência MIN/DETAIL. Cada valor abaixo mede, em ms no relógio nativo, a última notificação de publicação menos o início do primeiro wait do consumidor. Uma entrada independente contém os 32×4 IDs de rota da wave útil, quatro workers, cinco enqueues, cinco leituras e 0 ou 15 SET.

| Bloco | DENSE MIN | STAGED MIN | DIRECT MIN | DENSE DETAIL | STAGED DETAIL | DIRECT DETAIL |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 32,455 | 22,916 | 22,210 | 23,273 | 26,643 | 22,049 |
| 2 | 23,318 | 23,021 | 22,807 | 24,902 | 23,018 | 22,158 |
| 3 | 23,193 | 22,574 | 22,575 | 23,182 | 22,602 | 22,154 |
| 4 | 23,041 | 22,877 | 23,883 | 23,167 | 23,539 | 22,418 |
| 5 | 23,994 | 22,978 | 22,184 | 22,856 | 23,220 | 22,446 |
| 6 | 23,094 | 23,342 | 22,579 | 23,209 | 22,942 | 22,380 |

O ganho emparelhado de DIRECT em MIN contra STAGED foi +3,08%, +0,93%, −0,0041%, −4,40%, +3,45%, +3,27%. A mediana foi +2,00%, com 4/6 sinais positivos. Contra DENSE os seis ganhos foram +31,57%, +2,19%, +2,66%, −3,65%, +7,54%, +2,23%; mediana +2,45%, com 5/6 positivos. As medianas no retorno ao consumidor foram +1,98% e +2,34%, respetivamente. O limiar congelado para a publicação exigia pelo menos 5% e cinco sinais positivos em ambas as comparações. O verificador independente reavaliou os seis pares, os sinais e as comparações inclusivas com razões de inteiros. O maior ganho contra DENSE apareceu no primeiro lançamento físico. A dispersão por bloco é relevante nesta amostra.

| Layout | Mediana DETAIL/MIN publicação / wave externa | Pares dentro de ±15%, publicação / externa | READ worker-ms / união ms | SET worker-ms / união ms | União READ ou SET ms |
|---|---:|---:|---:|---:|---:|
| DENSE | 1,002 / 1,001 | 5/6 / 5/6 | 73,901 / 22,574 | 3,727 / 3,645 | 23,181 |
| STAGED | 1,006 / 1,006 | 5/6 / 5/6 | 73,453 / 22,434 | 3,645 / 3,606 | 23,102 |
| DIRECT | 0,986 / 0,984 | 6/6 / 6/6 | 72,926 / 22,254 | 0 / 0 | 22,254 |

A tabela apresenta as medianas de seis réplicas por layout. Os critérios numéricos de neutralidade adicional de DETAIL relativamente a MIN eram satisfeitos nos relógios observados. Em todas as 18 réplicas DETAIL a última publicação pertencia ao expert 49. O recibo compacta cada janela READ e SET em ns, relativa ao início do wait, com o worker, a geração, a posição da fila e o instante da publicação. Para os quatro workers, os tempos ocupados somam-se; no relógio da wave, READ e SET podem sobrepor-se. A parcela que cada SET acrescentou ao tempo do pedido continua desconhecida.

Houve 2 379 939 840 B pedidos em 180 preads ao pack parcial de 66 293 760 B e 1 586 304 000 B em 360 SET de DENSE/STAGED. O cgroup contabilizou 2 379 939 840 B lidos e 18 180 operações de bloco. Estes são contadores de âmbitos distintos. A família usou apenas o pack privado e o backend CPU. O tempo da família foi 66,780 s incluindo a C118 de 61 amostras em 60,138 s. O pico do cgroup foi 646 426 624 B, swap zero, sem eventos max/OOM. A monitorização observou CPU 61,625 °C, GPU 46,62 °C e NVMe até 34,85 °C. Os 36 processos terminaram e o pack conservou a identidade. O SHA-256 do recibo original é `0ee0617d1ed34f6e9a62f64395578f5d5909efce3d90921763a2863951dde52f`; o commit de execução é `b84f34c557b882c995b35d71d28b49ca90dc013d`. [Gate numérico anterior](../packed_real_layer/README.md)

O R02 exige os contadores minor e major cumulativos de `getrusage(RUSAGE_SELF)` imediatamente antes e depois do pré-toque e confirma cada delta antes de admitir o próximo braço. Nessa fronteira, os quatro workers ainda não foram iniciados. O protocolo conserva as mesmas seis permutações, janelas e critérios. O custo do serviço de cinco faltas é uma unidade diferente do custo do decode C293 e da conversa M4.

## Proveniência e reprodução

Depois de fechar a prova de exatidão CPU0 às 06:28 UTC, a atualização de pacotes da estação colocou a biblioteca NVML 620.73.04 junto do módulo carregado 620.70.06. A primeira janela de admissão para o custo terminou em `FAIL_INVENTORY` antes de lançar qualquer braço. O monitor da nova janela usou a NVML 620.70.06 já instalada localmente, SHA-256 `1b310cec5baddefef24c0d4b6cec982f1a58e2cc77454de7f7da9809bd9e9ad3`. O loader confirmou o ELF e a sonda confirmou o driver. A escolha afetou apenas o ambiente de monitorização. Cada filho CPU recebeu as bibliotecas GGML C269 congeladas. Os recibos e os dois conjuntos de binários ficaram no arquivo privado. [Identificação do monitor](monitor_library.py) · [Índice do lote 16](../private_archive/part-16.json)

Para repetir a execução, usar um diretório exclusivo por comando e a checkout limpa da revisão medida. A janela C55 requer a política e a biblioteca de telemetria correspondentes ao kernel em execução. O pack e o recibo de preparação são os da camada real. A compactação lê a revisão de `review.py` que a respetiva campanha usou. Os dois compactos foram reproduzidos, byte a byte, a partir do arquivo.

```sh
study=research/qualification-retake/packed_layer_service
python3 -B -m unittest discover -s "$study"
python3 -B "$study/build.py" --repo "$CLEAN" --backend "$C291" --libs "$C269_LIBS" --new-output-dir "$NEW_BUILD"
python3 -I -B "$study/profile.py" --checkout "$CLEAN" --expect-head "$HEAD" --build-dir "$NEW_BUILD" --build-sha256 "$BUILD_SHA" --input-dir "$TILE_INPUT" --input-sha256 "$INPUT_SHA" --libs "$C269_LIBS" --c55-receipt "$C55_RECEIPT" --c55-sha256 "$C55_SHA" --unit "$UNIT" --new-output-dir "$NEW_RUN"
python3 -B "$study/compact.py" --raw "$NEW_RUN" --study "$CLEAN/$study" --unit "$UNIT" --new-output-dir "$NEW_COMPACT"
```
