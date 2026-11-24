# Reprodução do build CUDA stock sem modelo

O [protocolo](protocol.md) fixa o pin, a ABI do serviço, os orçamentos, a verificação de SM89 e o limite da alegação. Compilar a partir de um repositório Git stock local que contenha o commit e a árvore completos. O diretório de trabalho e o destino do recibo devem ser novos, com os seus pais já existentes. O campo `scope_peak_bytes` inclui todas as tarefas e páginas cobradas pelo cgroup.

```sh
systemd-run --user --scope --quiet --collect --unit="$FRESH_UNIT" \
  --property=MemoryMax=6442450944 --property=MemorySwapMax=0 \
  python3 research/qualification-retake/stock_build/build.py \
  --llama-git "$LLAMA_STOCK_GIT" --private-root "$FRESH_PRIVATE_ROOT" \
  --new-output "$FRESH_RECEIPT_DIR"
```

A tentativa A terminou no checkout, em 0,728 s. O clone local original é shallow e anuncia refs de outro snapshot. O comando `git clone --local --shared --no-checkout` copiou essas refs e omitiu o objeto solicitado pelo checkout. Mantiveram-se o destino e o [FAIL](attempt-a/receipt.json). Na tentativa B o checkout tem uma nova base Git privada. `objects/info/alternates` aponta para os objetos imutáveis do clone local e a fronteira shallow é copiada para a nova raiz. A verificação explícita de commit e árvore antecede o CMake.

**PASS_STOCK_BUILD_AND_MODEL_FREE_CLI.** O servidor reportou versão 0.9.0-dev, build 1001 e commit `e95426f`. O SHA-256 do executável é `2396cc20738e1c2b7d8bfbe209b89098874683c424518d4bf139f7f51e9cfe00`. O conjunto stock resolveu oito bibliotecas do seu diretório de build. A inspeção do ELF CUDA encontrou 144 entradas de código SM89. O help confirma as 16 opções da API usadas no gate de arranque. O número de build deriva do histórico Git shallow local. CMake e Ninja produziram o servidor sem pesos nem pedidos ao modelo. [Recibo B](attempt-b/receipt.json)

O build B consumiu 488,968 s de parede, dos quais 484,881 s na compilação/ligação. O pico do cgroup foi de 3 059 544 064 B, o pico observado no disco de 431 939 584 B e o maior Tctl amostrado de 83,25 °C. Os eventos high/max/oom/oom_kill ficaram a zero. O recibo tem SHA-256 `089ff4f67b7914f075e67293c08a195a23af9cc2df49d3848815674f3f33bb52`; regista compiladores, flags, bibliotecas e hashes. A energia atribuível ficou desconhecida. A admissão da carga real tem [protocolo próprio](../stock_startup/protocol.md).
