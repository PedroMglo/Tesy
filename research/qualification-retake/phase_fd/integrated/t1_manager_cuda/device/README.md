# Ordenação no consumidor CUDA

**TESTADO sem GPU.** Os testes portáteis verificaram a aplicação da extensão ao source CPU autenticado, o encaminhamento dos nós, as verificações de providers e a rejeição de um evento ou de uma biblioteca obrigatória ausente. A primeira implementação gerou o source SHA-256 `feb6830bb037d8e4924afb33a2fe405036f0f62fc4b87a08727f632c633e0f31`. O freeze do protocolo é `9c543a25`. O comportamento do scheduler, a saída dos kernels e a transição CUDA→CPU exigem os processos físicos.

O ensaio usa o operador e o observador do antecessor CPU sob o scheduler misto. Em ORIGINAL, o segundo operando do CUSTOM CPU é a vista de quatro bytes do resultado mascarado que o backend CUDA produziu. O observador verifica o buffer host e lê a própria vista. No controlo EVENT, o pin expõe `ggml_backend_event_record` e `ggml_backend_event_synchronize`. O evento é gravado após a submissão no backend de computação. O worker recebe a conclusão e termina os três SET antes do drain global. Em BROKEN, o gate a montante só liberta o leitor após a sobrescrita terminada. Esse controlo força ordenação inversa sem acesso concorrente indefinido. O stream bruto e o join interno do CUDA não são exportados para a fixture. A identidade das bibliotecas fixa a implementação que liga estes eventos ao stream. Os prazos e garantias estão no [protocolo](protocol.md) e na [auditoria do pin](../../t1_manager_bank/cuda-consumers.md).

A compilação só precisa de headers pinados, compilador nativo e ELFs locais. O executável verifica as VMAs contra device/inode e nome do mapa autenticado em quatro pontos. O pai confirma os hashes, cada PID tem inventário C118 próprio e o filho aguarda o monitor com a CUDA ativa antes e depois da computação. O supervisor termina a família na primeira falha e preserva os logs. Os cinco processos incluem dois golds GPU independentes de agenda. Os dois positivos e o negativo usam o mesmo oráculo bitwise e escalar do antecessor CPU. O teste continua a ser de um operador sintético, com três projeções reais, sem modelo ou reserva do manager. [Oráculo numérico](../check.py) · [Fecho do controlo CPU](../README.md)

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_cuda/device
python3 -IB "$unit/test_device.py"
python3 -IB "$unit/build.py" --commit "$COMMIT_LIMPO" --backend "$C269" \
  --map "$STATIC_MAP" --new-output-dir "$BUILD_NOVO"
```

A medição pertence a uma janela própria, com o SHA do recibo de build previamente congelado e C55 vigente. O supervisor usa uma única unidade com cap de 2 GiB e swap zero. Cada filho confirma a entrada antes da inicialização e presta dois recibos enquanto detém os buffers da GPU. A duração limite da família é de 480 s, incluindo pelo menos 300 s de inventário. No portátil, o comando usa o diretório já autenticado de NVML do monitor.

```sh
systemd-run --user --scope --unit="$UNIT" -p MemoryHigh=2G -p MemoryMax=2G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=510 env LD_LIBRARY_PATH="$MONITOR" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$TESY_VENV/bin/python" -IB "$unit/run.py" \
  --commit "$COMMIT_LIMPO" --unit "$UNIT" --build-dir "$BUILD_NOVO" \
  --build-sha256 "$BUILD_SHA" --c55 "$C55" --c55-sha256 "$C55_SHA" \
  --ram-receipt "$RAM_RECEIPT" --map "$STATIC_MAP" --new-output-dir "$NOVO"
```

## Rejeição do primeiro arranque

**FAIL_PRESERVED.** Na tentativa `tesy-ordered-device-20261125-r01`, o primeiro gold OLD concluiu o inventário e terminou em stage 0. O guard recusou um objeto antes de chamar o backend. O stderr dizia apenas “unexpected ELF or VMA”. A identidade do primeiro objeto recusado nesse processo ficou desconhecida. Zero FFN, zero casos concorrentes e zero resultados de exatidão no dispositivo. [Recibo original](evidence/start-r01.json)

**REPRODUZIDO sem GPU.** O loader, em modo `--list`, resolveu os 16 objetos de arranque autorizados. Em 13 objetos no Btrfs deste host, `stat` fornece o dispositivo 0:40 e a VMA do mesmo FD fornece 0:38. O inode coincide. Uma sonda CPU mapeou uma página de cada ELF apenas como dados. Com a tabela original o guard rejeitou `/usr/lib64/libc.so.6`, inode 69729486, dispositivo VMA 0:38 contra dispositivo previsto 0:40. Com a tabela corrigida passou a identidade exata dos 21 providers, incluindo os opcionais. O caminho do primeiro esboço da sonda passiva apontava para o diretório pai errado em R02 e falhou antes do mapeamento. A identidade R03 preserva o sucesso. [Diagnóstico e digests](evidence/passive-r03.json)

O build passa a usar a rotina `reference_key` do qualificador de R0. O launcher continua a verificar stat completo e SHA-256. O filho continua a exigir caminho absoluto, dispositivo da VMA e inode em cada ponto de verificação e passa a registar o objeto recusado e as duas identidades. O build verifica ainda a resolução real do loader e recompila e executa a sonda CPU com a mesma função de validação do futuro filho. O novo source do filho tem SHA-256 `c0f5470716ebbe9a7b7a6fdfbb7984be1ea707a59dfe638fc9c8b008d56edeb0`. [Autoridade VMA do R0](../../../../nvme_r0_gate/qualified_profile/authority.py)

## Momento de atribuição do PID

**FAIL_PRESERVED R02.** O gold OLD completou a sua C118. Ambas as verificações de VMAs, `start` e `active`, passaram. O backend enumerou a RTX 4060 Laptop; o primeiro handoff exigiu o PID e a consulta devolveu zero proprietários. O processo parou antes de criar as suas matrizes, sem iniciar um FFN. Neste código a rejeição precedia a escrita da amostra no journal, que ficou vazio. O stderr original tem SHA-256 `6f78953e80453f0b2eb70183f189d2d1da1de2cfa717679acfaf427d9c31fa94` e a lista de providers em `active`, `b622ff4528aa23da1eae5399edcd260b6078bcbb9aab0872195db85200c47077`. [Recibo do processo](evidence/start-r02.json)

No pin C269, `ggml_backend_cuda_init` cria os metadados do backend e obtém o descritor do dispositivo (`ggml/src/ggml-cuda/ggml-cuda.cu:5824–5843`). A rotina de alocação do buffer CUDA seleciona o dispositivo e chama o allocator CUDA (809–825). Os SET usam cópia H2D com sincronismo do PTDS (714–719). R02 exigia a atribuição de PID logo após construir o backend, antes destas operações. A duração de um possível atraso da contabilidade NVML é desconhecida.

Na nova implementação o filho informa a entrada antes do init e a propriedade ativa após os SET concluídos das **12 componentes nas matrizes da própria fixture** e da máscara. O buffer permanece vivo até ao último handoff. Na entrada, a lista de processos de computação tem de estar vazia. No handoff ativo o supervisor só confirma quando observa exatamente o único PID esperado com o UUID qualificado. Se a lista ainda estiver vazia, admite no máximo três consultas, espaçadas por 50 ms e dentro de 2 s. Um UUID ou PID alheio, perda de proprietário durante o período ativo, falha de sensor, violação de recursos, ou prazo excedido encerra a família. Cada tentativa e rejeição deixa uma linha no monitor. O limite do ACK no filho continua em 3 s. O source prospectivo tem SHA-256 `aa045079b90fdfa17883f715b3feb6ca6cea080e3020ab5524e8b4ddd0052a05`. Os quatro testes portáteis passaram; as semânticas e os critérios de saída dos três braços concorrentes permanecem os do protocolo congelado.
