# Referência stock para o segundo turno Aster

**INCONCLUSIVE_BUDGET.** Com os 435 IDs históricos do segundo turno, o stock E10 produziu oito tokens. O primeiro ID coincidiu com o da sonda independente anterior e o servidor parou no limite de oito. Extrapolar os sete intervalos medidos para as 452 saídas históricas dá **20,15 / 28,73 / 44,91 minutos** para os dois pedidos. A média cabe nos 30 min, o cenário lento ultrapassa-os. O turno completo e a validação de Aster ficam por observar. M3 continua PARTIAL, com 19/20 no C133. [Pré-registo](protocol.md) · [Recibo físico](physical-r1/receipt.json)

| Relógio ou quantidade | Resultado |
|---|---:|
| Primer, slot 0 | 123 IDs novos, 1 saída, 82,913 s no cliente |
| Segundo pedido, slot 0 | 122 IDs reutilizados + 313 novos, 8 saídas, 227,212 s no cliente |
| Prefill / geração do segundo pedido, servidor | 204,922 / 22,289 s |
| Sete intervalos após o primeiro ID, mínimo / média / máximo | 2,043 / 3,184 / 5,336 s por passo |
| Custo fixo cobrado / tempo admissível por cada um dos 451 passos | 287,835 s / 3,353 s |
| Sensibilidade ao limite de 768 saídas, mínimo / média / máximo | 30,91 / 45,50 / 73,01 min |

O custo fixo inclui o primer inteiro, o prefill do segundo turno, 1 µs até ao primeiro endpoint de geração no relógio do servidor e 0,902 ms de overhead do cliente de T2. A decisão exige que os cenários fiquem do mesmo lado de 1 800 s. Os sete intervalos pertencem ao início da trajetória. Para uma saída de exatamente 452 tokens faltam **444 passos** depois dos oito observados. Restariam 1 489,876 s de pedidos, cerca de 3,356 s por passo restante. A evidência que falta é o custo dessa continuação, o término natural e a saída completa para o validador. O ensaio anterior mediu outro vetor de entrada no primeiro turno. [Referência com 122 IDs em cache](../aster_split/README.md) · [Custo do primeiro turno](../aster_budget/README.md)

**Execução física.** GPT-OSS-120B MXFP4 original no NVMe, stock e95426f, contexto 8192, SWA e KV completos, data C133, esforço medium, amostragem greedy e seed 42. O C55 admitiu E10. O C118 recolheu 61 amostras durante 60,183 s, em AC/performance, com a última às 03:57:13 UTC de 25 de novembro. A campanha demorou 404,226 s, incluindo 343,676 s de vida do servidor, prontidão aos 32,426 s e encerramento em 0,557 s. O filho encerrou com código zero após dois pedidos e nove tokens pedidos ao sampler. A janela autorizada admitia um arranque até às 04:06 UTC e término até às 04:18 UTC. [Precheck sem arranque](precheck-r1/receipt.json)

O pico do cgroup foi de 10 203 701 248 B, com high de 9,5 GiB, máximo de 10 GiB, swap zero e zero OOM. O pico de VRAM observado foi de 4 382 MiB. Nas 553 amostras do monitor, as máximas foram 70,0 °C na CPU, 50,35 °C na GPU e 57,85 °C no conjunto de sensores NVMe. O contador de pressão global de memória `full avg10` atingiu 5,54 e o mínimo de `MemAvailable` foi 25 527 107 584 B. O cgroup contabilizou 770 780 327 936 B lidos no NVMe e 1 011 712 B no segundo dispositivo em toda a vida acompanhada. Energia isolada desconhecida. O recibo identifica por SHA cada captura privada, incluindo o monitor e o stream com os oito endpoints. [Índice do arquivo privado](../private_archive/part-09.json)

Pré-registo `2e652b2f`, confirmação no commit `24f63873d2f2da1cf568f1e4458e8868498fe94b`, árvore `b61b8e0bb93c62d0f8dc13102eacad37d07c966b`. SHA-256 do precheck `ba7bd3bf704fbc26adc696213bc340a59eca2662b05955b4bb4141a3131206c7` e do ensaio físico `75d34fe5420d78176f9ea7269c41dca1224108cb6ff7072cf59442988b39b209`.

Para reproduzir no portátil, partir dessa checkout limpa e apontar para a política C55 válida com o respetivo recibo, o placement verificado, o build stock e o raw da sonda anterior. `SPLIT_RAW/response-2.json` é a resposta privada com SHA-256 `69e794547cc271732a71b3139af88b89cbe709ad3504527e4174bc3fd91baddb`. O precheck usou a mesma entrada com `--before-inventory-only` e destinos exclusivos próprios. O comando abaixo corresponde à tentativa física.

```sh
systemd-run --user --scope --quiet --collect --unit="$NEW_UNIT" \
  --property=MemoryMax=10737418240 --property=MemoryHigh=10200547328 \
  --property=MemorySwapMax=0 --property=IOAccounting=yes \
  python3 -B research/qualification-retake/aster_turn2_budget/probe.py \
  --expect-head 24f63873d2f2da1cf568f1e4458e8868498fe94b \
  --historical-results "$C7/results" --prior-second-response "$SPLIT_RAW/response-2.json" \
  --policy "$C55_POLICY" --placement "$VERIFIED_PLACEMENT_RECEIPT" \
  --binary "$STOCK_BUILD/build/bin/llama-server" \
  --build-receipt research/qualification-retake/stock_build/attempt-b/receipt.json \
  --original-jinja "$STOCK_BUILD/source/models/templates/openai-gpt-oss-120b.jinja" \
  --new-raw "$NEW_PRIVATE" --new-output "$NEW_SUMMARY"
```
