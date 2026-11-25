# Último leitor CUDA e reposição antes do primeiro decode

**GO para testar a integração com o grafo completo.** O FFN real na CUDA conseguiu ler os pesos da geração antiga enquanto o manager C291 já tinha quatro reservas pendentes para a tile seguinte. A reposição preservou os 40 membros, os slots, os 120 hashes dos pesos e o vetor completo do primeiro FFN de decode. Quando os workers receberam autorização para sobrescrever antes do leitor, todas as 2 880 coordenadas do FFN anterior mudaram, apesar de o primeiro decode continuar bit a bit igual. Preservar só o estado final deixaria passar este erro. [Protocolo](protocol.md) · [Recibo sanitizado](receipt.json) · [Fixture CPU e FAIL preservado](../README.md)

| Braço GPU | Libertação dos SET | Claims e publicações | Preads do pack | SET | Leitor da tile A | Primeiro decode |
|---|---|---:|---:|---:|---|---|
| Reference | Vista escalar, seleção original | 45 | 45 | 135 | Geração antiga | Igual |
| Disk | Evento CUDA, reposição pelo pack | 51 | 47 | 153 | Geração antiga | Igual |
| Bank | Vista escalar, uma reposição pela RAM | 51 | 46 | 153 | Geração antiga | Igual |
| Broken | Sobrescrita antes do leitor | 51 | 46 | 153 | Geração nova | Igual |

Quatro workers serviram as reservas e dois preloads da primeira wave B. O FFN correu sobre os três tensores primários MXFP4 de 2 880 × 2 880 × 40 do próprio manager. Executou as três projeções `MUL_MAT_ID`, a SwiGLU-OAI, a máscara e a redução na CUDA. O leitor de A usou a segunda linha da última wave, com dois ranks ativos, incluindo dois slots também usados para parking na primeira linha. Na Reference e no Bank, a callback CPU autorizou o primeiro SET depois de receber uma vista escalar de quatro bytes dependente das três projeções. Disk esperou por um evento explícito no backend CUDA. O primeiro remap de decode devolveu [6,7,2,4], com os quatro ranks ativos. As referências numéricas antiga e nova foram calculadas fora da transição no mesmo backend, sobre as gerações correspondentes. A comparação cobre cada byte dos vetores finitos.

Cada braço perturbado leu para a RAM quatro registos residentes na GPU para permitir a permutação (52 876 800 B), além de ter capturado os 13 219 200 B do expert 6 antes da reserva. A reposição exigiu seis publicações com 18 SET do host para a GPU, num total de 79 315 200 B de payload. Em relação à mesma reposição por disco, o Bank evitou um pedido ao FD de 13 221 888 B. A Reference manteve a seleção original e dispensou esses seis jobs. São contagens dos pedidos e payloads da fixture. O tráfego físico do NVMe e dos barramentos e o tempo de parede recuperável continuam por medir.

**Execução e limites.** Protocolo congelado em `3f0e5948`. Build e execução na checkout limpa `92ed7b3d`, com C55 e um C118 de 61 amostras antes de cada braço. O build demorou 6,894 s e a família 248,789 s, incluindo os quatro inventários. Houve um processo por braço e quatro leituras de recursos entre a entrada e a saída de cada um. O pico amostrado da GPU foi 608 MiB, com 2 MiB antes e depois de cada processo. Os máximos observados foram 57,375 °C na CPU, 44,15 °C na GPU e 33,85 °C no NVMe. O pico do scope foi de 443 510 784 B, com limite de 2 GiB e swap zero. O supervisor validou o pack sintético de 79 552 512 B através do descritor e removeu-o no fecho.

O ensaio cobre uma camada, duas tiles pequenas com rotas prescritas e uma linha FFN por fronteira. Para admitir um ensaio de tempo de produto, falta demonstrar a equivalência de rotas, máscaras, KV e logits completos, incluindo o primeiro decode, no grafo e geometria do pedido. Falta também cobrar o custo de capturar, coordenar, transferir e repor no pedido natural. Não houve forward de modelo, e o ensaio não altera M3 PARTIAL nem M4 NOT_MET.

O verificador reconstitui as waves, gerações e custos a partir dos jobs, identifica as bibliotecas observadas, autentica o build, os registos do processo, os inventários e os ficheiros de floats. Dois destinos exclusivos reproduziram o recibo SHA-256 `b6782dffda2e6ab91dbc369d769514ff80764a0099371ad71d629f18d5eaa660`. A família original tem SHA-256 `7759c83fbac31506f2ab3455dd4ae813445ed5633e24e44ab5a769470bc4e42a`. O manifesto do arquivo privado `part-58` tem SHA-256 `482b58c73614cf484aacb10f73632c6d071fa92eb941514d243c90453a4215c9`. Os testes de schema e fronteiras lógicas correm em CPU sem pesos.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_bank/tile_transition/device
python3 -IB "$unit/test_run.py"
python3 -IB "$unit/test_operator.py"
python3 -IB "$unit/compact.py" --family "$RAW" --receipt-sha256 "$RAW_SHA" \
  --build "$BUILD" --c55 "$C55/receipt.json" --new-output "$NEW"
cmp "$unit/receipt.json" "$NEW/receipt.json"
```
