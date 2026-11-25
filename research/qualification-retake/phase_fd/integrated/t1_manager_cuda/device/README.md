# Ordenação no consumidor CUDA

**TESTADO sem GPU.** Dois testes portáteis verificaram a aplicação da extensão ao source CPU autenticado, o encaminhamento dos nós, as verificações de providers e a rejeição de um evento ou de uma biblioteca obrigatória ausente. O source CUDA gerado tem SHA-256 `feb6830bb037d8e4924afb33a2fe405036f0f62fc4b87a08727f632c633e0f31`. O freeze do protocolo é `9c543a25`. O comportamento do scheduler, a saída dos kernels e a transição CUDA→CPU exigem os processos físicos.

O ensaio usa o operador e o observador do antecessor CPU sob o scheduler misto. Em ORIGINAL, o segundo operando do CUSTOM CPU é a vista de quatro bytes do resultado mascarado que o backend CUDA produziu. O observador verifica o buffer host e lê a própria vista. No controlo EVENT, o pin expõe `ggml_backend_event_record` e `ggml_backend_event_synchronize`. O evento é gravado após a submissão no backend de computação. O worker recebe a conclusão e termina os três SET antes do drain global. Em BROKEN, o gate a montante só liberta o leitor após a sobrescrita terminada. Esse controlo força ordenação inversa sem acesso concorrente indefinido. O stream bruto e o join interno do CUDA não são exportados para a fixture. A identidade das bibliotecas fixa a implementação que liga estes eventos ao stream. Os prazos e garantias estão no [protocolo](protocol.md) e na [auditoria do pin](../../t1_manager_bank/cuda-consumers.md).

A compilação só precisa de headers pinados, compilador nativo e ELFs locais. O executável verifica as VMAs contra device/inode e nome do mapa autenticado em quatro pontos. O pai confirma os hashes, cada PID tem inventário C118 próprio e o filho aguarda o monitor com a CUDA ativa antes e depois da computação. O supervisor termina a família na primeira falha e preserva os logs. Os cinco processos incluem dois golds GPU independentes de agenda. Os dois positivos e o negativo usam o mesmo oráculo bitwise e escalar do antecessor CPU. O teste continua a ser de um operador sintético, com três projeções reais, sem modelo ou reserva do manager. [Oráculo numérico](../check.py) · [Fecho do controlo CPU](../README.md)

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_cuda/device
python3 -IB "$unit/test_device.py"
python3 -IB "$unit/build.py" --commit "$COMMIT_LIMPO" --backend "$C269" \
  --map "$STATIC_MAP" --new-output-dir "$BUILD_NOVO"
```

A medição pertence a uma janela própria, com o SHA do recibo de build previamente congelado e C55 vigente. O supervisor usa uma única unidade com cap de 2 GiB e swap zero. Cada filho presta dois recibos de handoff enquanto detém a GPU. A duração limite da família é de 480 s, incluindo pelo menos 300 s de inventário. No portátil, o comando usa o diretório já autenticado de NVML do monitor.

```sh
systemd-run --user --scope --unit="$UNIT" -p MemoryHigh=2G -p MemoryMax=2G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=510 env LD_LIBRARY_PATH="$MONITOR" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$TESY_VENV/bin/python" -IB "$unit/run.py" \
  --commit "$COMMIT_LIMPO" --unit "$UNIT" --build-dir "$BUILD_NOVO" \
  --build-sha256 "$BUILD_SHA" --c55 "$C55" --c55-sha256 "$C55_SHA" \
  --ram-receipt "$RAM_RECEIPT" --map "$STATIC_MAP" --new-output-dir "$NOVO"
```
