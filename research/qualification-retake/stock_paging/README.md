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
