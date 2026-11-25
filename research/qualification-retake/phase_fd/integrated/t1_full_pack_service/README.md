# Entrega dos quatro grupos a partir do ficheiro integral

**MEDIDO no portátil — GO_COST_42_STRATA.** Com os 29 experts nos seus offsets originais do pack integral, mudar simultaneamente a disposição de leitura e a política de expulsão reduziu o serviço mediano das quatro waves em **47,91% e 47,34%**, nos dois processos. Na fatia compacta, os processos históricos mediram **62,18% e 62,46%**. O sinal persiste, mas a fatia sobrestimou a redução observada na colocação integral. O protocolo admite orçamentar a amostra de 42 estratos. Os dados vêm de quatro waves selecionadas por divergência das políticas, sem forward do Transformer. M3 continua PARTIAL e M4 NOT_MET. [Recibo com os blocos](evidence/physical.json) · [Protocolo congelado](protocol.md) · [Controlo da fatia](../t1_native_sink/README.md)

### Comparações emparelhadas

A e B usam LRU, respetivamente com GGUF e pack. C e D expulsam primeiro os residentes com cópia, respetivamente com GGUF e pack. A unidade temporal é a soma das quatro janelas de serviço, de despacho até à conclusão dos SET e sincronização por wave. Cada mediana usa quatro blocos num processo, após uma passagem de exatidão. Os rácios são calculados dentro do bloco antes de tirar a mediana.

| Localização e processo | A (ms) | B (ms) | C (ms) | D (ms) | D face a A | D face a B (política no pack) | D face a C (pack na nova política) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Integral 1 | 124,59 | 84,71 | 95,37 | 65,03 | 47,91% | 23,31% | 31,54% |
| Integral 2 | 123,70 | 83,41 | 96,07 | 65,27 | 47,34% | 21,85% | 32,07% |
| Fatia 1 | 125,02 | 60,76 | 95,37 | 47,45 | 62,18% | 22,52% | 50,22% |
| Fatia 2 | 123,95 | 59,84 | 95,96 | 46,49 | 62,46% | 22,04% | 51,41% |

Cada um dos três contrastes pré-registados foi favorável em **4/4 blocos de cada processo integral**, acima dos 3/4 exigidos. Medianas absolutas D face a A de 59,66 e 58,51 ms. A redução relativa por bloco variou de 46,64 a 48,08% no primeiro processo e de 47,18 a 78,98% no segundo. O bloco 1 deste último conserva A a 313,72 ms e D a 65,95 ms. As outras três observações de A ficaram entre 123,58 e 123,80 ms. O recibo inclui as quatro observações, sem exclusões. [Dados por bloco](evidence/physical.json)

Isoladamente, o pack sob LRU (B face a A) reduziu 31,94% e 32,56% no integral, contra 51,36% e 51,71% na fatia. Já a mudança de política sobre o GGUF (C face a A) reduziu 23,83% e 22,33% no integral, contra 23,73% e 22,57% na fatia. A perda de magnitude concentra-se assim no contraste da leitura do pack. As comparações entre épocas são descritivas. A diferença absoluta pode também refletir os extents físicos e o estado do dispositivo. [Rácios e interação por bloco](evidence/physical.json)

| Waves incluídas | D face a A, integral 1 / 2 | D face a A, fatia 1 / 2 | D face a B, integral 1 / 2 | D face a C, integral 1 / 2 |
|---|---:|---:|---:|---:|
| Call de 148, CPU | 39,97 / 40,64% | 56,66 / 56,42% | 7,76 / 6,96% | 34,19 / 34,70% |
| Call de 148, CUDA | 47,49 / 46,69% | 62,40 / 62,96% | 29,24 / 24,06% | 22,56 / 22,89% |
| Decode, CPU | 51,00 / 49,44% | 64,65 / 65,28% | 34,55 / 32,96% | 27,55 / 27,80% |
| Decode, CUDA | 99,94 / 99,94% | 99,95 / 99,93% | 99,90 / 99,88% | +4,08 / −18,17% |

Somando as duas janelas da call de 148 dentro de cada bloco, D face a A reduziu 42,05% e 42,00%. Nas duas janelas de decode reduziu 66,00% e 64,48%. Todos esses contrastes tiveram 4/4 sinais favoráveis. Na wave CUDA do decode, C e D já servem os quatro experts no primário, zero leituras e zero SET. Aí a comparação do pack D face a C oscilou em cerca de seis microssegundos por célula, com apenas 2/4 e 1/4 sinais favoráveis no integral e 3/4 e 1/4 na fatia. Esta wave testemunha o efeito da política sobre os acessos. [Contabilidade por célula e estrato](evidence/physical.json)

### Contabilidade, recursos e auditoria

Por passagem das quatro waves, A/B têm 10 hits primários, um no banco e 18 leituras de experts. C/D têm 11, quatro e 14. A/B/C/D fizeram respetivamente 54/18/42/14 leituras do FD e 57/57/54/54 SET. As cinco passagens das quatro células custaram **4 232 704 000 B pedidos aos FDs por processo**. A preparação leu mais 767 152 128 B em cada processo. Os 1 740 hashes dos componentes nas saídas nativas foram confirmados por processo, incluindo CPU e CUDA. A produção da cópia integral teve um custo separado de 61 096 329 216 B lidos na origem, escritos e relidos no destino, 356,60 s de cópia, 46,65 s de releitura e 464,20 s totais. [Custos e verificação](evidence/physical.json) · [Colocação](../../../packed_nvme_placement/protocol.md)

As C118 tiveram 61 amostras cada em 60,19 / 60,17 s. Os picos do cgroup foram 946 401 280 / 924 295 168 B sob cap de 2 GiB e swap zero. Máximos de VRAM 608/608 MiB, CPU 64,38/62,88 °C, GPU 47,94/47,65 °C, NVMe 53,85/46,85 °C. Preparação, inicialização dos backends e cleanup demoraram, respetivamente, 1,778/1,735 s, 0,262/0,261 s e 0,018/0,013 s. No último sample de cleanup os buffers tinham sido libertados e o PID da fixture ainda detinha o contexto CUDA, com 102 MiB de uso total da GPU em ambos. Os processos foram sequenciais. [Recursos por processo](evidence/physical.json)

A medição usou commit `43403f179ce98f43a450736000e3a44bd21f9d3e`, árvore `943ed76f455d3bb1e212e02ce8c52a46c40db7d4`. O revisor, executado novamente só em CPU, autenticou os recibos físicos `24d6461356bbb7bca7be96bc779e3dde2e48555dbd8a4af37ba5cd0437f0d408` e `ee0f410fed882e54e18b064f6b5f448150b7469dfb03975c645bdafc1d4caca2`, a C55 `41255a25d222f56d2d28a60a7e028e8a21101425d166581ec5b4e067e2673c7c` e a colocação `adc58125a13aa286371c127f41bf67b0ed4756e9ec2dc08bd2cb6e7ed754a000`. Reconstituiu a decisão e um recibo de 63 325 B idêntico byte a byte à primeira revisão, SHA-256 `47e5b06abe3674b11354ae1ffb90257aaa66cdb972a3e6f1c9a5d14334825936`, em 0,07 s e 27 748 KiB de RSS. [Recibo público](evidence/physical.json) · [Condições para regressar ao endpoint](product-path.md)

O lote privado 51 arquiva os dois processos e as revisões em 12 ficheiros, 260 069 B. O SHA-256 do manifesto é `fbc06b13116a4f6b0746457fe84dd1601ad4af5cda1b66cbe85360384cc6bcb8`. O revisor aceita as raízes copiadas e revalida journals e recibos.

## Reprodução

O plano selado fixa 29 registos e 87 componentes. O verificador da preparação conferiu os 29 offsets reais, digest `6e09c22efa24a4945bf9fcea0701b3dbcc4102a44bb58b83ab1b1c45f7df8f88`. A seleção vem da mesma conversa, do mesmo banco e das mesmas duas políticas da fixture anterior. A primeira célula só abre depois de a colocação integral estar autenticada e as janelas selecionadas, incluindo o padding, reproduzirem o digest da fatia. [Protocolo](protocol.md)

A medição exige uma checkout limpa, um recibo PASS da colocação, o SHA-256 desse recibo fixado para a família, o GGUF original já colocado, uma C55 dentro da validade, C118 por braço e a identidade do monitor/driver que passou na fixture dos destinos nativos. Usar o mesmo ambiente dessa fixture, quatro workers e um scope novo por processo. Usar uma nova raiz privada por comando. Os argumentos `ARM1` e `ARM2` identificam as unidades sem sufixo.

```sh
cmd=(python3 -IB "$UNIT_DIR/measure.py" --commit "$FROZEN_COMMIT"
  --placement "$PLACEMENT/receipt.json" --placement-sha256 "$PLACEMENT_SHA"
  --model "$MODEL" --plan "$PLAN" --map "$STATIC_MAP" --ram-dir "$HISTORICAL_RAM")
systemd-run --user --scope --unit="$ARM1" -p MemoryHigh=2G -p MemoryMax=2G -p MemorySwapMax=0 \
  -p RuntimeMaxSec=230 env LD_LIBRARY_PATH="$MONITOR" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  "${cmd[@]}" --arm 1 --unit "$ARM1" --c55 "$C55" --c55-sha256 "$C55_SHA" --new-output-dir "$FIRST"

systemd-run --user --scope --unit="$ARM2" -p MemoryHigh=2G -p MemoryMax=2G -p MemorySwapMax=0 \
  -p RuntimeMaxSec=230 env LD_LIBRARY_PATH="$MONITOR" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  "${cmd[@]}" --arm 2 --unit "$ARM2" --c55 "$C55" --c55-sha256 "$C55_SHA" \
  --first-dir "$FIRST" --first-sha256 "$FIRST_SHA" --new-output-dir "$SECOND"
```

O revisor aceita dados arquivados, confirma os tempos diretamente nos journals e preserva os quatro sinais por contraste, tier e fase. Não abre o pack ou o modelo. A comparação com a fatia reporta os dois processos históricos em separado. Uma nova C55 para o segundo processo pode ser fornecida em `--second-c55`.

```sh
python3 -IB "$UNIT_DIR/review.py" --first "$FIRST" --first-sha256 "$FIRST_SHA" \
  --second "$SECOND" --second-sha256 "$SECOND_SHA" --c55 "$C55" --placement "$PLACEMENT/receipt.json" \
  --placement-sha256 "$PLACEMENT_SHA" --plan "$PLAN" --ram-receipt "$HISTORICAL_RAM/receipt.json" \
  --map "$STATIC_MAP" --new-output-dir "$NEW_AUDIT"
```

Os testes sintéticos distinguem offsets integrais e compactos com as mesmas matrizes, rejeitam um endereço de outro expert e recusam um manifesto de tamanho, origem, digest ou estado incorretos. O revisor anterior continua a reproduzir o recibo histórico `c70cb5b267cc26877f8d353c8cdb27c6f7334b392be6c9983ddbbad61e6f57fe` a partir dos seus dois processos. [Resultados anteriores](../t1_native_sink/README.md) · [Censo das 42 waves](../t1_full_workload/README.md)

## Viabilidade de alargar a amostra

O programa atual conserva em memória um exemplar dos pesos de cada expert selecionado para preparar e verificar os destinos. Nos 42 estratos, os 310 registos exigiriam **4 097 952 000 B apenas para estes exemplares**, ultrapassando o cap de 2 GiB antes dos pools e do scratch. O plano de 42 estratos ainda pediria **21 426 974 720 B ao FD por processo** nas cinco passagens de serviço. Uma extensão teria de limitar os exemplares vivos por wave ou subgrupo estável, repetir a preparação fora do relógio e contar essas leituras e a ordem dos acessos no novo orçamento. [Censo selado](../t1_full_workload/evidence/receipt.json)

A soma das quatro células do mesmo censo, incluindo todas as waves dos domínios de prefill e decode, alcança 110 521 798 656 B por passagem de serviço (54 520 057 856 B nas calls 5+148). Cinco passagens custariam 552 608 993 280 B por processo antes de verificação, preparação e reconstituição do estado do primário. São bytes previstos pelas agendas congeladas. O pack integral permite estudar os offsets originais; não remove estes custos. A medição dos quatro grupos pode decidir se vale orçamentar primeiro os 42 estratos.
