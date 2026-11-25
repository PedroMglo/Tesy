# Admissão da observação do pack no cliente natural

A medição completou os quatro braços e os oito pedidos. Os raws originais e a cópia arquivada produziram a mesma graduação dos turnos e o mesmo resultado do journal. [Resultados, custos e reprodução](review.md)

A recompilação sem instrumentação diferiu do C291 original em 19 secções alocadas, incluindo `.text`. A regra prospetiva exige portanto **quatro servidores, pela ordem BASE, CONTROL, OFF, ON**. Em todos, o servidor original C281 usa o mesmo pack. O contraste CONTROL/BASE isola a recompilação, OFF/CONTROL inclui o código de observação inativo e ON/OFF ativa a escrita durante T2. As semelhanças e diferenças das bibliotecas foram verificadas no build estático. Os resultados da conversa dependem de uma fonte de dados separada. [Protocolo do cliente](protocol.md) · [Adenda da toolchain](toolchain.md) · [Protocolo do build](../dso/current-toolchain.md)

O supervisor verificou offline as cinco execuções da fixture C291, os recibos de build e os seus fornecedores. A tentativa inicial da fixture nativa ficou preservada antes dos casos e a primeira tentativa do build DSO terminou antes da candidata. O build R02 e a fixture R02 passam os gates estáticos. O cliente exige ainda que os três braços do **C292 com pack** apontem aos mesmos ELF, aos originais por SHA e à árvore C127/C270 verificada de 3266 ficheiros, 88 704 231 B. A janela C55 de produto começa depois do fecho desse C292. [Ponte numérica e âmbito](../numeric/protocol.md)

Uma execução completa do bloco anterior de três braços levou 620,5–631,5 s. Para quatro, a previsão é de aproximadamente 14 min de bloco e 60 s adicionais de C55. O máximo do bloco é 2600 s, 256 MiB, quatro novos processos e oito pedidos de geração. Cada processo tem C118 própria de 60 s, E20 com stop de 19,5 GiB, swap zero e confirmação da saída e da porta. [Custos históricos](../../../../../packed_nvme_manifest/server_profile/conversation/ordens.md)

O controlo do C292 R01 terminou com código zero. O supervisor falhou ao procurar `startup_count` após a saída. A família R02 usa a medição desse PID e as quatro observações independentes do FD aberto em O_DIRECT. O revisor numérico reabre o controlo em R01 e os dois overlays em R02, compara as três árvores completas e vincula os resultados por SHA. A conversa exige o recibo dessa reprodução, os monitores e os lançamentos originais, as graduações de cada braço e o ficheiro de amostras do FD. O relógio do scope CONTROL ficou por observar no relatório R01. [Método de reabertura](../numeric/reopen.md) · [Revisor numérico](../numeric/review.py)

O protocolo do gatilho, a alimentação por IDs ordenados, o revisor SSE e os relógios vêm dos supervisores anteriores. A banda descritiva é aplicada a doze razões T2, quatro por contraste. A validação do PFJ pertence ao auditor independente. A conclusão host de um SET CUDA não prova o instante do último consumidor na GPU; o seu custo exposto só admite os limites que o grafo e os dados da própria execução sustentarem. [Auditor do journal](../natural_trace/analyse.py)

### Preparar e executar na checkout congelada

Usar uma pasta inexistente por preparação e outra por execução. O operador obtém os SHA de C55 e C292 dos respetivos recibos terminais e verifica que a sua C55 continua válida em cada spawn. O comando abaixo usa Bash e a mesma autoridade histórica de C281/C292. O segundo comando com `--execute` destina-se apenas à janela física autorizada.

```bash
D="$FROZEN/research/qualification-retake/igpu_resident_rank/request_budget/device/pack_native/conversation"
ARCHIVE=/mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01

opts=(--repo "$FROZEN" --commit "$COMMIT" --unit-prefix "$NEW_UNIT_PREFIX"
  --method toolchain --bridge-dir "$NEW_C292" --bridge-sha256 "$NEW_C292_SHA"
  --bridge-failed-dir /var/tmp/tesy-c292-pack-numeric-physical-20261125-r01
  --bridge-fds-dir /var/tmp/tesy-c292-pack-numeric-control-fds-20261125-r01
  --bridge-review "$C292_REVIEW/receipt.json" --bridge-review-sha256 "$C292_REVIEW_SHA"
  --window "$NEW_C55" --window-sha256 "$NEW_C55_SHA"
  --placement /tmp/tesy-nvme-placement-20261124-01/receipt.json
  --c270 /tmp/tesy-c270-driver-20261125-r01/receipt.json
  --c270-sha256 1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6
  --preflight-dir /tmp/tesy-env49-static-r01
  --preflight-sha256 2508e245fcde7ff411c93474919c3701ac95e98c1f76505d74a248d34a6aff16
  --history-dir "$ARCHIVE/part-23/tesy-c281-driver-20261125-r01"
  --closure-dir /tmp/tesy-c281-pack-link-20261125-r01
  --derived-dir /home/pmglo/models/tesy-gpt-oss-120b-nvme/tesy-c291-manifest-20261125-r02
  --constructor-receipt /tmp/tesy-pack-manifest-constructor-20261125-r02/receipt.json
  --c292-receipt "$ARCHIVE/part-54/c292-nvme-numeric-pair-20261125-r01/receipt.json"
  --build-dir /tmp/tesy-c291-pack-pfj-dso-20261125-r02
  --build-sha256 cfd616fda7fcdac7aaf6774f9b6d2aac7ea5186a5629fa33eb1bff58a00b34c8
  --fixture-dir /tmp/tesy-pack-native-pfj-20261125-r02
  --fixture-sha256 625b0e50c920938e478ff5b2f2a8bd0c85bbe2fb1f78fa4278f0e040f2ea3759)

python3 -IB "$D/test_family.py"
python3 -IB "$D/test_bridge.py"
python3 -IB "$D/family.py" "${opts[@]}" --new-output-dir "$PREPARED"
python3 -IB "$D/family.py" "${opts[@]}" --prepared "$PREPARED/family.json" \
  --prepared-sha256 "$PREPARED_SHA" --execute --new-output-dir "$NEW_RAW"
```

O prefixo de unidade começa por `tesy-c281-nvme-`. Em cada pasta de braço `receipt.json` preserva o resultado natural do cliente e as identidades dos descritores. `arm.json` regista a graduação e o digest do recibo. Em ON, `journal-audit.json` acompanha o PFJ selado em `raw/events.pfj`. O resultado da família pode associar trabalho natural válido a um journal incompleto; o campo `journal_status` conserva essa distinção.
