# Referência de projeção e diagnóstico por bloco

**Os 2880 F32 da projeção gate de e28, antes do bias, foram reproduzidos bit a bit.** A referência usa apenas a ativação de CPU0 na posição 189 e os 4 406 400 B do peso gate já colocado no NVMe. O verificador confrontou duas implementações na mesma entrada. Os 90 blocos Q8_0 coincidiram com a função exportada pelo ELF CPU C269. Cada uma das 2880 linhas calculadas pela reconstrução também coincidiu com o dot do ELF. [Entrada autenticada](../input.md) · [Protocolo](protocol.md) · [Recibo](receipt.json)

| Comparação | Extensão | SHA-256 comum |
|---|---:|---|
| Quantização reconstruída e `quantize_row_q8_0` da C269 | 3060 B | `2a8187b4c60ab35286840ce35ba28d8671ff7a6a07149cf59abfdf4009cea6ef` |
| Gate reconstruído e `ggml_vec_dot_mxfp4_q8_0` da C269 | 11 520 B | `756c8384a4cda89c62040a81d3e45dd06e0707121dcbadecc73d45ecec0e1db3` |

A preparação foi fechada em `b0dfb79ad48575a83826d876c2a34073d395b192`, sob o protocolo de `5c16f4f9`. Em seguida, três chamadas independentes de `cmp` verificaram os ficheiros do braço físico ALIAS. As duas projeções desse braço (grafo de quatro ranks e grafo de um rank) coincidiram integralmente com a linha acima. A requantização recolhida na fixture física coincidiu com os 3060 B. Este último dado verifica a mesma entrada e função do ELF. O callback físico observa diretamente a saída da projeção. SHA-256 do recibo físico `34f504b177c8878290513a8aa45d725cf54eae5915ba9f351579f503b5dd2ca7`; SHA-256 do recibo desta reconstrução `77af85bff7e65de6c084268da4f665c2cb01e56df61e00084692b98b153d8cc1`.

A reconstrução usa o arredondamento F32 para os códigos Q8_0 e a escala F16 guardada. Para cada linha, expande os nibbles, calcula oito somas inteiras por bloco e aplica `fmaf` a cada escala e acumulador. A soma final reproduz a separação dos blocos pares/ímpares e a árvore horizontal do AVX2. A igualdade foi verificada nesta entrada e neste peso. Três testes sintéticos cobrem o empate na quantização, números pequenos, cancelamento em acumuladores diferentes e a extração de códigos/escalas de Q8_1 x4. A preparação R01 leu 4 406 400 B do pack, demorou 1,88 s de parede, consumiu 1,87 s de CPU em user e atingiu 32 500 KiB de RSS. Estes valores descrevem a reconstrução em Python. [Aritmética](arithmetic.py) · [Verificador](screen.py)

Para repetir na checkout selada, usar o bundle da parte 74, o recibo da colocação integral e o diretório do backend C269. `NEW` designa uma pasta ainda inexistente.

```sh
prlimit --as=268435456 --cpu=60 -- env -i PATH=/usr/bin:/bin LC_ALL=C OMP_NUM_THREADS=1 \
  /usr/bin/python3 -IB screen.py prepare --backend "$C269" --bundle "$BUNDLE" \
  --placement "$PLACEMENT_RECEIPT" --new-output-dir "$NEW"
cmp "$NEW/receipt.json" receipt.json
cmp "$NEW/gate.f32" "$ALIAS_PROJECTION/gate-rank0.f32"
cmp "$NEW/gate.f32" "$ALIAS_PROJECTION/single-rank0.f32"
cmp "$NEW/activation.q8" "$ALIAS_PROJECTION/activation.q8"
```

`screen.py diagnose --help` dá a interface para uma futura saída candidata e digests obtidos dos recibos. Havendo um RHS Q8_1 x4 efetivo, o diagnóstico compara os bits das escalas e os códigos usados pelo dot nos 90 blocos; a soma adicional e as duas posições de padding ficam fora da comparação. A projeção condicional mantém a árvore de redução CPU para isolar o efeito de mudar o RHS. Sem os bytes desse operando, apenas a comparação das linhas de saída é identificável.
