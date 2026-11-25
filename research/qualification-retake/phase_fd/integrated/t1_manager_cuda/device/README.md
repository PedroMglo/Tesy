# Ordenação no consumidor CUDA

**MEDIDO na RTX 4060 Laptop. PASS_CUDA_WAVE_FIXTURE_ONLY.** O observador CPU recebeu uma vista escalar produzida pelo FFN na CUDA0. Ao autorizar a substituição do slot nesse observador, a saída completa conservou os 32 valores da geração antiga, bitwise. O controlo com evento explícito no backend CUDA produziu o mesmo resultado. Quando autorizámos a substituição apenas pelos IDs e atrasámos o consumidor até aos três SET, o FFN devolveu exatamente a geração nova. Nos três braços, o banco continha os mesmos 1 632 B antigos e as doze componentes do primário terminavam com os mesmos 6 528 B. Esta é uma prova de ordenação da wave no operador. A integração na reserva real e a fronteira entre tiles continuam em aberto. [Recibo físico revisto](evidence/physical.json) · [Protocolo congelado em 9c543a25](protocol.md)

| Processo | Geração usada no FFN | SHA-256 dos 32 F32 | Duração total do filho (s) |
|---|---|---|---:|
| OLD, gold isolado | Antiga | `1e1e6519…1b6981f` | 1,167 |
| NEW, gold isolado | Nova | `6ebc5310…9ef77537` | 1,011 |
| ORIGINAL, vista da wave | Antiga | `1e1e6519…1b6981f` | 1,145 |
| EVENT, evento após submissão | Antiga | `1e1e6519…1b6981f` | 1,017 |
| BROKEN, sobrescrita antes da leitura | Nova | `6ebc5310…9ef77537` | 1,102 |

A revisão reconstruiu os pesos a partir dos nibbles e expoentes MXFP4 dos slots arquivados e avaliou up/gate/down, SwiGLU e o rank que sobrevive à máscara em float64. O maior erro absoluto em relação a esse oráculo foi 2,24×10⁻⁷ nos braços da geração antiga e 5,60×10⁻⁶ nos da nova, dentro da tolerância prospetiva de 10⁻⁴. As cinco saídas coincidiram também com as saídas CPU da mesma geração. O efeito temporal da captura continua por medir. Os tempos da tabela incluem inicialização, handoffs com o monitor e saída do filho.

**Recursos.** Houve 305 amostras C118 em 300,869 s e 20 amostras de serviço. Nos cinco processos o monitor passou de zero proprietários na entrada para o único PID do filho no UUID esperado na fase ativa e no fim do FFN, e voltou a zero após a saída. As leituras de VRAM total foram 2 / 104 / 114 / 2 MiB. Cada handoff passou na primeira consulta. Foram verificados 16 objetos mapeados no arranque e 19 em cada um dos três pontos seguintes. O intervalo entre a primeira amostra de inventário e a última amostra de serviço foi 306,987 s. O pico do cgroup foi 218 189 824 B, sob o limite de 2 GiB e com swap zero no scope. Os máximos observados foram 51,75 °C na CPU, 38,87 °C na GPU e 33,85 °C no NVMe. Zero forwards de modelo e zero leituras de pesos 120B.

**Proveniência.** R03 partiu de `b1b406eb4ee72e3296715a77fb1af0baaf4ea34e`, árvore `01123325dba08e683f56675d42addbb7dcd9c923`. O recibo de build tem SHA-256 `7fbd8b368bf617b9c364c82ab90d925d740701748451ea8f6ea6b1389f71bc0c` e o recibo físico `20d66fe68189cb44b6871089619a30c6850058e093dac77c4f28e981da366155`. A parte 53 preserva os 137 ficheiros e 1 281 816 B do manifesto `3beb53b8731ea7eb5dbbf491cdc8e2075898300c923df0e54104516fd58f9409`. Duas reanálises, uma com os diretórios locais de execução e outra diretamente na parte 53, produziram o mesmo compacto sanitizado SHA-256 `f589f6bd57667f8d985c1d4a854eef92a1df8fa629d235706adf892e892147c1`. R01 e R02 permanecem na secção de falhas abaixo.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_cuda/device
python3 -IB "$unit/review.py" --runs-root "$PART53" --manifest "$PART53/manifest.json" \
  --map "$STATIC_MAP" --c55 "$C55_R02" --new-output-dir "$NOVA_REVISAO"
cmp "$NOVA_REVISAO/receipt.json" "$unit/evidence/physical.json"
```

## Operador e reprodução física

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
