# Primeiro decode CPU0 com três residentes e uma falta

**MEDIDO no portátil.** O manager C291 preservou e28, e8 e e16 nas posições e gerações observadas em C270 e leu e24 pela fila original. Os braços COPY e ALIAS reproduziram bit a bit os 2 880 valores F32 do primeiro decode CPU0. A referência C127 tinha executado o cálculo com os 128 experts no namespace lógico e a captura C270 confirmou o resultado. [Gold e pré-estado](../../decode_reference/protocol.md) · [Protocolo](protocol.md) · [Recibo compacto](evidence.json)

| Braço | Cópias na instalação dos 3 residentes | Bytes devolvidos nas 3 preads de preparação | Bytes devolvidos na única pread após o corte | Componentes iguais no consumidor | F32 diferentes |
|---|---:|---:|---:|---:|---:|
| COPY | 39 665 664 B | 39 776 256 B | 13 258 752 B | 24/24 | 0 |
| ALIAS | 0 B | 39 776 256 B | 13 258 752 B | 24/24 | 0 |
| WRONG | 0 B | 39 776 256 B | 13 258 752 B | 22/24 | 2 880 |

A contraprova trocou apenas gate.weight entre 28 e 24 depois do remap e antes da primeira multiplicação. Os dois hashes trocaram de posição, a saída permaneceu finita e os quatro ranks, os pesos de routing e a tabela de slots permaneceram idênticos aos dos braços corretos. Os três MUL_MAT_ID em CPU usaram diretamente as vistas CPU_Mapped; os três ADD_ID conservaram os IDs lógicos dos biases. A intervenção abrange a preparação de três registos imutáveis e o seu consumo por uma linha real do FFN. O modo COPY conservou uma segunda janela física de 13 221 888 B por residente; ALIAS conservou uma referência. O volume de leituras concluídas no FD O_DIRECT é igual nos três braços. O volume de NAND e o tempo do pedido não são identificados nesta fixture.

| Expert, em ordem de rank | Estado observado antes | Posição após a procura |
|---:|---|---|
| 28 | READY s3/g6 | s3/g6 |
| 24 | ABSENT_RELOAD | s14/g6 |
| 8 | READY s6/g5 | s6/g5 |
| 16 | READY s35/g4 | s35/g4 |

O corpus é log_medium de 189 tokens até ao primeiro decode. Os três READY constam dos 55 experts da última tile de prefill [160,189). Na fixture, três preads antes do corte materializam os dados desses residentes. A máscara de elegibilidade fixa s14 para a única falta. A fixture deixou s14/g5 sem ocupante materializado e protegeu os 36 outros slots. Posteriormente, uma reconstrução independente das sete waves inferiu os 40 donos e identificou e11 como vítima em s14/g5. O recibo desse estudo tem SHA-256 `bebcd9273232b6623a381b4eba8de87a7c48818bb82eaf9e6e8ec8b45f74a2aa`. As idades, pontuações de retenção e várias gerações continuam por determinar. A descoberta posterior não foi usada nos três braços físicos. [Reconstrução de slots](../../decode_reference/last_wave/protocol.md) A fixture justifica a exatidão deste corte parcial, sem reconstruir os 189 tokens, o KV, os logits finais ou a latência do cliente. A experiência das três tiles de anchor-nominal153 usou outro workload. [Três tiles e permutas](../README.md)

O scope E4 teve pico 293 195 776 B, swap zero e nenhum OOM. As três janelas C118 e o monitor passaram. A família durou 182,803 s, incluindo os 180 s de inventário. O nativo abriu o pack C290 verificado por FD e leu diretamente quatro registos completos por braço, incluindo os biases; não abriu o GGUF. A etapa seguinte que justificaria maior alcance é testar a última tile real do mesmo pedido e o seu estado de saída antes desta procura. M3 continua PARTIAL e M4 NOT_MET.

## Reprodução

Checkout limpa `ccd5242131946c501624c9d975150c5095bffad5`. Protocolo `6d92bff1`, build `b083a55c45c4ed02e8ceea74e8fe3c47ada92204cac5a8f995511e8741960f6d` e recibo físico `1e96e86946bc9c10fb39f2bee1c62d379f9feddc891502b2892e64c517cba723`. C55 deve ainda ser válido em cada arranque. Usar nomes de scope e diretórios novos.

```sh
python3 -IB "$STUDY/build.py" --backend "$C7/backends/c291-expert-store" \
  --libs "$C269_LIBS" --new-output-dir "$NEW_BUILD"
systemd-run --user --scope --quiet --unit="$UNIT" -p MemoryMax=4G -p MemoryHigh=4G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=890 env LD_LIBRARY_PATH="$MONITOR_NVML" \
  python3 -IB "$STUDY/profile.py" --commit "$HEAD" --unit "$UNIT" --build-dir "$NEW_BUILD" \
  --build-sha256 "$BUILD_SHA" --input-dir "$TILE_PREP" --reference-dir "$GOLD" \
  --placement-receipt "$PLACED/receipt.json" --prestate-receipt "$PRESTATE/receipt.json" \
  --libs "$C269_LIBS" --c55-receipt "$C55/receipt.json" --c55-sha256 "$C55_SHA" \
  --new-output-dir "$NEW_RUN"
```
