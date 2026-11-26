# Admissão do smoke CPU ik com as primeiras 16 posições C110

Esta decisão precede a janela de capacidade e qualquer abertura para inferência.
Uma janela passiva de 60 s com `nvme_admission/window.py` observa o NVMe e o
`app.slice` de destino e preserva a política C55 canónica. Aplica-se o menor
teto indicado pelos dois observadores. Preferir E20 (20 GiB). Se **todos**
os restantes critérios passarem e faltar margem para E20, admitir apenas uma
unidade separada E10 (10 GiB) desde que ambos os tetos cheguem a 10 GiB.
O `NOT_ADMITTED` da C55 E20 permanece no arquivo. Uma falha de sensor, energia,
inatividade, espaço ou proveniência impede ambos; abaixo de 10 GiB param ambos.
Idade máxima da última amostra 55 minutos no arranque de cada C118. Expiração
exige C55 nova. Mudanças de envelope não autorizam retentar após uma falha de
execução. Reserva-se o servidor e o perfil operacional E20 para estudos próprios.

Reutilizar o contrato FILE_PAGING de `stock_numeric/run.py` e
`tools/host_resource_policy.py`: cgroup v2 MemoryMax=cap, MemoryHigh=cap−512 MiB,
MemorySwapMax=0. MemoryHigh permite reclaim de cache de ficheiro. Os limites
de anon, PSI, reclaim, OOM, swap, térmicos e reserva externa são os do
RuntimeGuard canónico; o pico de memory.current é cobrado mesmo se for file.
A parte mapeada tem 63 387 346 208 B virtuais. Deixar RLIMIT_AS livre e
observar VmSize/VmPeak além de memory.current/peak/stat/pressure, RSS/PSS,
faults e io.stat, incluindo o namespace físico separadamente. Estes contadores
referem-se ao processo, ao cgroup ou ao dispositivo conforme a origem.
C55 e C118 de 60 s, AC/performance, NVML compatível de monitor, sem compute
GPU. Após o sinal do coordenador, cada modo arranca em scope e raiz exclusivos,
faz a sua C118 e valida-a no intervalo de 3 s. Arquivo privado até 64 MiB.
Orçamento por processo de 180 s para carga/contexto, 90 s para a chamada de
16 e 90 s para a chamada de 1, 10 s para encerramento. Uma infração termina
o grupo de processos e verifica a saída; conservar todos os recibos, inclusive
interrupção e restart supervisionado com nova identidade.

Usar o GGUF NVMe com colocação autenticada pelo SHA integral
`582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d`.
C55 faz apenas stat. A preparação invoca `stock_numeric.evaluate.inputs`,
que reabre os seis controlos A/B/C de C109/C110. Os primeiros 16 IDs i32 LE
têm SHA `d6a1f114bb22668e36cf1eaf1af14861b4e5b9a688704b06aff5298ecbb25a8d`;
com o teacher 976 na posição 16, `378eeb5ae41c80e16df38faad214c82e138727d2ddc1723a44f09c29c6e0f75c`.
Os dois vetores de 201 088 F32 LE nas posições 15 e 16 têm respetivamente SHA
`da1de57d5c7f736a9156271f1f80669e040727347494b3ac3f7bba5b73e3be9b` e
`c813e8fb7e6bb5401ae800c27171fd32e0da02977c678a494d4f8f7c32cf3a1e`.
Apenas se a posição 15 for finita com máximo único 3659 pode o processo executar
o teacher 976. Conservar valores e comparar posição 16 com gold (máximo único 3992 obrigatório),
top-5 ordenado, palavras diferentes, erro máximo, MAE e RMSE. Distinguir
igualdade integral, ordem coincidente e diferenças numéricas sem limiar de
equivalência. O smoke de 17 entradas CPU-only do fork é uma comparação ao
canário C110 P12 heterogéneo com 32 slots, e ao stock e95426f quando os raws
estiverem autenticados. Não extrapolar a uma conversa, M3, M4 ou desempenho.
