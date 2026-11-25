# Primeira projeção gate real de e28 na CPU

**A linha pré-bias de e28 foi capturada no grafo CPU0 dos quatro ranks.** Os 2 880 F32 são finitos. O mesmo MUL_MAT_ID com apenas a matriz de e28 produziu exatamente os mesmos bits. A saída do FFN completo também reproduziu os 2 880 F32 de C127/C270. [Recibo](receipt.json) · [Referência, inputs e hashes de origem](../input.md)

| Resultado privado | Forma / bytes | SHA-256 |
|---|---:|---|
| Gate, rank 0 dos quatro | 2 880 F32 / 11 520 B | `756c8384a4cda89c62040a81d3e45dd06e0707121dcbadecc73d45ecec0e1db3` |
| Gate, uma matriz e ID local 0 | 2 880 F32 / 11 520 B | `756c8384a4cda89c62040a81d3e45dd06e0707121dcbadecc73d45ecec0e1db3` |
| Entrada convertida pelo quantizador CPU Q8_0 | 90 blocos / 3 060 B | `2a8187b4c60ab35286840ce35ba28d8671ff7a6a07149cf59abfdf4009cea6ef` |
| FFN da camada 0, posição 189 | 2 880 F32 / 11 520 B | `6bc70d200ac08db00f6c3fa34098bd660d2ba4bc4c02368de319cbadf6167333` |

O callback já subscrito recebeu em CPU o resultado [2880,4,1,1] do MUL_MAT_ID com a vista MXFP4 original. Conferiu os ranks lógicos 28, 24, 8 e 16, as slots 3, 14, 6 e 35 e a geração 6 da slot 3. O consumidor seguinte do gate confirmou que esse mesmo tensor alimentou o ADD_ID do bias gate. O subgrafo usou 24/24 componentes corretas, três registos de preparação e uma falta de 13 258 752 B. Os quatro workers terminaram. O quantizador foi aplicado separadamente à linha F32 para conservar uma referência do lado direito do produto. [Protocolo](protocol.md)

A C118 durou 60,191 s, com 61 amostras. O processo filho durou 0,162 s incluindo I/O, hashing e os dois grafos. A família durou 61,166 s, atingiu 232 570 880 B no cgroup de 4 GiB e manteve swap zero. O relógio do filho não isola o custo de uma projeção. A comparação futura na iGPU deve usar o ficheiro `ALIAS/projection/gate-rank0.f32` contra a sua saída antes do bias. O âmbito desta medição é um rank numa posição de uma conversa.

## Reproduzir

Usar a checkout limpa `d83a6e70269fccdf3ad13d72cd398d30e8351bfe`, o build anterior `b083a55c…60f6d`, uma janela C55 admissível e destinos privados novos. As identidades dos inputs e dos executáveis constam do recibo. Os dados derivados ficam na raiz privada da campanha.

```sh
python3 -IB "$STUDY/build.py" --old-build "$SHAPE1_BUILD" --libs "$C269_LIBS" --new-output-dir "$BUILD"
systemd-run --user --scope --quiet --unit="$UNIT" -p MemoryMax=4G -p MemoryHigh=4G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=370 env LD_LIBRARY_PATH="$MONITOR_NVML" \
  python3 -IB "$STUDY/profile.py" --commit "$FROZEN" --unit "$UNIT" --old-build "$SHAPE1_BUILD" \
  --build-dir "$BUILD" --build-sha256 "$BUILD_SHA" --libs "$C269_LIBS" --input-dir "$TILE_PREP" \
  --reference-dir "$DECODE_REFERENCE" --placement-receipt "$PLACED/receipt.json" \
  --prestate-receipt "$PRESTATE/receipt.json" --c55-receipt "$C55/receipt.json" \
  --c55-sha256 "$C55_SHA" --new-output-dir "$RUN"
```
