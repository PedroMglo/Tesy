# Arranque E20 do 120B com paginação sob demanda

**MEDIDO — PASS_EXPERIMENTAL_LAZY_MMAP_E20_READY_ONLY.** No portátil, o carregador experimental chegou a READY em **8,3321 s** com o GGUF original de 120B no NVMe interno, cap de 20 GiB e swap zero. O filho encerrou normalmente. O resultado abre a comparação numérica no 120B. Primeiro conteúdo final, exatidão dos logits no 120B, decode e conversa sustentada continuam por medir neste candidato. M3 permanece PARTIAL e M4 NOT_MET. [Protocolo congelado](protocol.md) · [Recibo físico](physical-r1/receipt.json)

## Execução de 25 de novembro de 2026

| Fase | Observação | Decisão |
|---|---|---|
| Fixture CPU com GGUF sintético | Stock, OFF e ON deram os mesmos 64 logits em dois prompts. Identidade CPU e mudança de prefault observadas. Opção inválida rejeitada. | Pré-requisito cumprido. [Recibo independente](../stock_prefault_resident/attribution-r2/receipt.json) |
| C55 R01 | 60,32 s de processo. O observador suplementar encontrou o contrato histórico C281 ausente na checkout esparsa. Zero cargas de modelo. | FAIL_INVENTORY preservado. [R01](c55-r1/receipt.json) · [Reparação congelada](window-repair.md) |
| C55 R02 | Após incluir o contrato versionado, 62 amostras em 61,0002 s, depois do PASS da fixture CPU. Ambas as estimativas admitiram 22,5 GiB com reserva de 2 GiB. | PASS_RESOURCE_WINDOW_ONLY. [R02](c55-r2/receipt.json) |
| Pré-verificação E20 | 0,0691 s, zero servidores e zero pedidos. O linker selecionou a candidata e sete bibliotecas stock. | PASS_MODEL_FREE_PRE_INVENTORY. [R01](precheck-r1/receipt.json) |
| C118 e arranque ON | C118 de 61 amostras em 60,1810 s, AC/performance. Uma carga, READY aos 8,3321 s, encerramento em 0,2965 s e filho terminado com código 0. | 8,6313 s desde o lançamento até à recolha do filho, 69,5103 s no supervisor incluindo C118. [R01](physical-r1/receipt.json) |

A medição usou a checkout limpa `8f204b4204762dbb12e46bfd024b166bcc17e8df`, árvore `1ebd2847e5c832193599311ff69083f9860ab6e7`. O executável stock do pin `e95426f16982054c379ca7bdc8186996dd22f0fe` recebeu a biblioteca candidata com `TESY_STOCK_LAZY_MMAP=1`. Em READY o processo mapeava a candidata, os sete DSOs originais, o próprio executável e o GGUF de 63 387 346 208 B. A libllama original estava ausente. O log confirmou 36 camadas e 161 slots MXFP4, duas KV de 8192 células com 288 MiB cada na GPU, um slot de conversa, ub32 e o Jinja com a data congelada. O recibo inclui os digests dos quatro raws, do modelo, das bibliotecas pertinentes e dos programas. [Build e gold](../stock_prefault_build/build-r1/receipt.json) · [Recibo físico](physical-r1/receipt.json)

O cliente enviou zero pedidos HTTP e pediu zero tokens. O warmup explícito estava desligado. O servidor executa internamente a sonda de remoção de KV com dois IDs antes de inicializar os slots. O contador final deste braço registou 262 faltas de experts, zero hits e 3 302,98 MiB enviados para ubatches de até oito IDs. Os 262 payloads de 13 219 200 B correspondem a 3 463 430 400 B entregues para cópia host→CUDA. O teor dos logits desta sonda ficou por observar. [Origem e semântica dos contadores](../stock_log/README.md)

## Recursos e relógios

| Observação | Valor |
|---|---:|
| Pico exato de memória no cgroup / high / max | 16 982 515 712 B (15,816 GiB) / 19,5 GiB / 20 GiB |
| Máximos amostrados no cgroup, anon / file / file_mapped | 316 755 968 / 16 449 171 456 / 4 029 784 064 B |
| Máximo amostrado RSS / PSS do servidor | 5 146 767 360 / 5 139 091 456 B |
| Swap, memória bloqueada e eventos high/max/OOM | 0 |
| Pico de VRAM total amostrada | 4 348 MiB |
| Máximos amostrados CPU Tctl / GPU / NVMe composto | 57,375 / 45,53 / 41,85 °C |
| Máximos de PSI de memória full avg10, anfitrião / cgroup | 1,38% / 0,00% |
| Leituras físicas do namespace NVMe (259:0), desde antes do spawn até à recolha | 17 249 456 128 B (16,065 GiB) |
| Leituras atribuídas ao cgroup pelo io.stat, no mesmo dispositivo | 17 203 736 576 B (16,022 GiB), 164 578 operações |
| Raw total / limite | 114 646 B / 64 MiB |

Os 15 pontos do monitor abrangem o processo. As categorias de residência têm interseções e os seus máximos podem ocorrer em amostras diferentes. O namespace contabiliza todas as leituras físicas no dispositivo, incluindo as que não são atribuídas ao cgroup. O seu limite era 1 TiB. O estado inicial da page cache é desconhecido. A potência instantânea da GPU variou entre 2,76 e 10,91 W nas amostras. A energia atribuível à execução é desconhecida. Após o encerramento, o coordenador observou a unidade systemd inativa e a GPU em 2 MiB e 43,26 °C. [Recibo e hashes da telemetria](physical-r1/receipt.json)

## O que esta observação altera

O stock E20 histórico terminou antes de READY por PSI full persistente. A referência stock E10 já atingira READY e processara pedidos. A exploração atual estabelece que o derivado ON pode inicializar o 120B em E20 nas condições observadas. Os braços vieram de janelas diferentes, sem emparelhamento de page cache ou carga do anfitrião. A causalidade da alteração de prefault e o eventual deslocamento de leituras para o primeiro pedido permanecem em aberto. O próximo gate é a paridade dos logits completos na mesma entrada 120B contra stock independente e o mesmo derivado OFF, com geometria e estado de entrada qualificados. Para medir produto seguem-se braços contemporâneos com história real, primeiro conteúdo final, decode e resposta validada, incluindo as guardas do outro caso. [Stock E20 histórico](../aster_ram_budget/README.md) · [Stock E10](../aster_budget/README.md)

## Reprodução do procedimento congelado

Este protocolo fixa o fecho às 04:52 UTC de 25 de novembro de 2026. O comando abaixo documenta a entrada usada. Atribuir a `MEASURE` a checkout de medição, a `STOCK` o diretório do build B pinado, a `OVERLAY` o diretório do build experimental R01, a `ATTRIBUTION` o recibo físico R02 da fixture CPU, a `POLICY` a política canónica da C55 R02 e a `PLACEMENT` o recibo da colocação NVMe. Cada invocação usa uma unidade e duas saídas privadas novas. A opção final aplica-se exclusivamente ao pré-check.

```sh
run_ready() {
    unit=$1
    raw=$2
    summary=$3
    shift 3
    systemd-run --user --scope --quiet --collect --unit="$unit" \
      --property=MemoryMax=21474836480 --property=MemoryHigh=20937965568 \
      --property=MemorySwapMax=0 --property=IOAccounting=yes \
      python3 -B "$MEASURE/research/qualification-retake/stock_prefault_ready/start.py" \
      --expect-head 8f204b4204762dbb12e46bfd024b166bcc17e8df \
      --policy "$POLICY" --placement "$PLACEMENT" --binary "$STOCK/build/bin/llama-server" \
      --build-receipt "$MEASURE/research/qualification-retake/stock_build/attempt-b/receipt.json" \
      --original-jinja "$STOCK/source/models/templates/openai-gpt-oss-120b.jinja" \
      --overlay-root "$OVERLAY" --attribution-receipt "$ATTRIBUTION" \
      --new-raw "$raw" --new-output "$summary" "$@"
}
run_ready "$PRECHECK_UNIT" "$NEW_PRECHECK_RAW" "$NEW_PRECHECK_REPORT" --before-inventory-only
run_ready "$PHYSICAL_UNIT" "$NEW_PHYSICAL_RAW" "$NEW_PHYSICAL_REPORT"
```

SHA-256 dos recibos integrais do pré-check `bc2a290312eacf3c1d22c263287374c73138b28835a9d0820af1cc28e2ffbe89` e do arranque `b8263c6c1640d7878140013cf2baaf7039c215acbe0d331916af14f9eab04d01`. [Entrada](start.py) · [Testes sem modelo](test_ready.py)
