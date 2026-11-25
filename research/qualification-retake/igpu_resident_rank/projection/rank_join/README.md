# O rank e28 recompõe o FFN C127 no primeiro decode

**Os 2880 F32 da contribuição ponderada de e28 coincidiram bit a bit com o grafo CPU.** A soma dessa contribuição com as três contribuições CPU originais, na ordem do grafo, também reproduziu os 2880 F32 do FFN C127. Decisão `GO_COMPOSED_E28_CONTRIBUTION_AND_FFN` para a posição 189, camada CPU0, rank lógico 0, expert 28, slot 3, geração 6. Os dados provêm de processos separados. A composição foi feita offline. [Pré-registo](protocol.md) · [Recibo integral](receipt.json)

| Fronteira verificada | Diferenças observadas |
|---|---:|
| Projeções RADV gate e up de e28 vs. linhas CPU | 0/2880 F32 em cada |
| Gate e up após o bias lógico vs. quatro segmentos submetidos ao shader de ativação | 0/2880 F32 em cada |
| Saída F32 do SwiGLU RADV vs. CPU | 979/2880, máximo absoluto 2⁻²¹, até 5 ULP |
| Operando efetivo do down RADV vs. CPU | 0/90 escalas FP16, 0/2880 códigos i8 |
| Buffer Q8_1 produzido pelos dois processos RADV sobre o mesmo SwiGLU | 0/3312 bytes |
| Projeção down de e28 antes e depois do bias vs. CPU | 0/2880 F32 em cada |
| Contribuição de e28 após multiplicar pelo seu peso de routing | 0/2880 F32 |
| Redução das quatro contribuições vs. FFN C127 | 0/2880 F32 |

O revisor somou de forma independente os três biases originais de e28. Os três `pread` no pack selado devolveram 34 560 bytes no total. Os SHA individuais por papel e os offsets absolutos constam do recibo. A primeira projeção usada foi gate de e28 e o controlo gate de e24 também correspondeu à sua referência CPU. No down, trocar os pesos de e28 pelos de e24 mantendo a ativação de e28 alterou 2880/2880 coordenadas. [Gate e up nas alocações GGML](../primary_import/) · [Ativação](../rank_activation/) · [Down e seu controlo](../rank_down/)

Para recompor o FFN, o revisor aplicou em F32 a soma com o bias down e o produto pelo peso do router. Depois somou as contribuições na ordem `((e28 + e24) + e8) + e16`, com arredondamento a cada adição. As três últimas contribuições vieram da captura CPU de quatro ranks. A contribuição de e28 tem SHA-256 `c474bd5218a08f310d58e58ef13d1a8f32a8d2212f1c3ee2728594f34fcf785d`, e o FFN tem SHA-256 `6bc70d200ac08db00f6c3fa34098bd660d2ba4bc4c02368de319cbadf6167333`. As conclusões sobre a ativação F32, o resultado da contribuição e o resultado do FFN têm denominadores próprios. Continua por medir a integração de um consumidor RADV vivo com os outros ranks, os leases do manager e o relógio do cliente. [Referência CPU](../rank_cpu/)

O pré-registo ficou congelado em `2aaeac4c`, o revisor em `6322336361c8dfe0978156c1dd576e4d16f8eced` e o recibo tem SHA-256 `4f630197df4b475bcbd2ff3508c36e839748e97779472628705b7a85b1a61b31`. Para reabrir no mesmo portátil, usar as quatro pastas privadas autenticadas pelos hashes do recibo e o diretório do manifesto derivado C291 R02. A verificação relê os três biases e compara as saídas existentes.

```sh
D=research/qualification-retake/igpu_resident_rank/projection/rank_join
python3 -IB "$D/test_review.py"
python3 -IB "$D/review.py" --cpu-dir "$CPU_R01" --primary-dir "$PRIMARY_R01" \
  --swiglu-dir "$SWIGLU_R01" --down-dir "$DOWN_R01" \
  --down-sha256 d9fc9e22380bc42560fec18c066db4decd1a857c835a7b0a6ecfc98dbcf132d9 \
  --manifest-dir "$MANIFEST_C291_R02" --new-output-dir "$NEW_REVIEW"
```
