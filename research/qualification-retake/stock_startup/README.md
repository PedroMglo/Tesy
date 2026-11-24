# Admissão de um único arranque

O [protocolo](protocol.md) fixa uma carga, zero pedidos e o stop preventivo do operador. O [runner](start.py) usa o recibo da cópia e a política C55 do NVMe, verifica o build stock e executa o inventário C118 imediatamente antes do filho. O próprio scope deve ter `MemoryMax=cap`, `MemoryHigh=cap−536870912` e `MemorySwapMax=0`. As raízes para raw e recibo têm de ser distintas e novas. Ambas conservam falhas.

```sh
python3 research/qualification-retake/stock_startup/test_startup.py
systemd-run --user --scope --quiet --collect --unit="$FRESH_UNIT" \
  --property=MemoryMax="$CAP_BYTES" --property=MemoryHigh="$HIGH_BYTES" \
  --property=MemorySwapMax=0 --property=IOAccounting=yes \
  python3 research/qualification-retake/stock_startup/start.py \
  --policy "$C55_POLICY" --placement "$NVME_PLACEMENT_RECEIPT" \
  --binary "$STOCK_SERVER" --build-receipt "$STOCK_BUILD_RECEIPT" \
  --new-raw "$FRESH_PRIVATE_RAW" --new-output "$FRESH_RECEIPT_DIRECTORY"
```

Na verificação dirigida, a tentativa de comparar `stat.st_dev` com o device exibido em `/proc/self/maps` falhou para o mesmo inode de um ELF visível na estação. O runner reutiliza a [prova por FD e VMA do mesmo ficheiro](../cuda35/vma_identity.py). Para o GGUF, mantém um descritor aberto, confere o inode, tamanho, mtime e ctime com a colocação verificada e observa a identidade da VMA de uma página mapeada passivamente. A leitura integral pertence ao recibo NVMe. As fixtures exercitam a separação bind/prontidão, a geometria incompleta, o primeiro I/O de um novo cgroup, a substituição por outro inode do mesmo tamanho e a rejeição do scope antes do spawn.

**R1 NOT_RUN.** O validador recusou o envelope sem o dicionário exterior `limits` antes de abrir o modelo ou criar o servidor. O estado original e o hash do runner ficaram no [recibo](r1/receipt.json). A nova identidade usa `{"limits": {}, "resources": ...}` sem duplicar limites. A fixture de falha do scope passa agora uma política C55 completa pela derivação e pelo validador reais. A opção `--before-inventory-only` aplica a política do dia e verifica no cgroup prescrito o recibo da colocação, o binário e as bibliotecas; termina imediatamente antes de C118. O ensaio físico usará o inventário completo e a mesma margem de memória do protocolo original.
