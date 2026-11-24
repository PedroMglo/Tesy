# Startup stock em FILE_PAGING v3

As duas entradas de modelo usam o mesmo binário e argumentos. A entrada desta unidade fixa o cap em 10 GiB e entrega ao kernel o reclaim aos 9,5 GiB. Os resultados históricos R1/R2 conservam a sua receita e podem ser reproduzidos no commit `b9c99a53ef497f5064d3af883ba92702d0b305a3`. O novo [protocolo](protocol.md) define o que constitui uma carga admitida e os limites de medição.

O verificador dirigido é `python3 research/qualification-retake/stock_paging/test_paging.py`. A fixture seguinte cria um único ficheiro esparso numa raiz nova em filesystem de disco, com propriedade do projeto. A saída compacta fica numa segunda raiz nova.

```sh
systemd-run --user --scope --quiet --collect --unit="$FIXTURE_UNIT" \
  --property=MemoryMax=50331648 --property=MemoryHigh=33554432 \
  --property=MemorySwapMax=0 python3 research/qualification-retake/stock_paging/reclaim.py \
  --new-private-directory "$FRESH_DISK_DIRECTORY" --new-output "$FIXTURE_RECEIPT"
```

O precheck, com `--before-inventory-only`, termina depois de validar a política real, o cgroup, o recibo de colocação e os ELFs. A carga de modelo usa a mesma forma de invocação com novas raízes e sem essa opção, após a liberação da estação.

```sh
systemd-run --user --scope --quiet --collect --unit="$FRESH_UNIT" \
  --property=MemoryMax=10737418240 --property=MemoryHigh=10200547328 \
  --property=MemorySwapMax=0 --property=IOAccounting=yes \
  python3 research/qualification-retake/stock_paging/loader.py --before-inventory-only \
  --policy "$C55_POLICY" --placement "$NVME_PLACEMENT_RECEIPT" \
  --binary "$STOCK_SERVER" --build-receipt "$STOCK_BUILD_RECEIPT" \
  --new-raw "$FRESH_PRIVATE_RAW" --new-output "$FRESH_RECEIPT_DIRECTORY"
```

## Resultado no portátil

**READY medido; FAIL na prova de colocação.** Com o GGUF verificado no NVMe interno, um servidor stock no cap E10 chegou a `model loaded`. O journal marcou 34,885 s e o observador verificou prontidão aos 35,446 s desde o spawn. A camada do servidor confirmou uma sequência com 8192 posições. A saída deu código 0 aos 36,061 s. Não houve pedidos de cliente nem warmup. O prazo de carga distingue-se do tempo até ao primeiro conteúdo final. [Recibo físico](startup-r1/receipt.json)

O cgroup atingiu 10 203 201 536 B, com 140 251 eventos high, 17 803 460 pgsteal e zero eventos max, OOM ou swap. Nos 56 pontos observados o máximo de file foi 9 892 671 488 B e o máximo de memória anónima foi 320 057 344 B. O maior Locked foi zero e a VRAM total amostrada atingiu 4070 MiB. O NVMe 259:0 contabilizou 82 552 700 928 B de leitura, incluindo trabalho de prefetch/releitura do arranque. O intervalo máximo das amostras do filho foi 0,850 s. Os três hashes do raw foram verificados após encerramento. A [fixture esparsa](fixture-r1/receipt.json) havia demonstrado reclaim com 85 eventos high, 38 176 pgsteal e zero blocos alocados no disco. O [precheck](precheck-r1/receipt.json) validou a política real, o scope e as identidades antes da admissão.

O nível efetivo 3 emitiu o marcador READY mas omitiu a colocação CPU_Mapped, a cache CUDA, o grupo de 36 camadas com 161 slots e os KV de 8192/256 células. O veredito congelado permaneceu FAIL. Para identificar estas alocações basta o callback da biblioteca emitir as mensagens GGML INFO, convertidas pelo pin em TRACE de nível 4. A observação autoriza qualificar esse diagnóstico independentemente sem modelo. O arranque E10 não mediu uma conversa, qualquer logit ou ganho de desempenho. [Conversão de nível no pin](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/common/log.cpp#L546-L571)
