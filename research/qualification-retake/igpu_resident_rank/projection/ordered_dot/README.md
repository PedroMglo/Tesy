# O mesmo gate no Ryzen e na Radeon integrada

**MEDIDO no portátil em 25 de novembro de 2026.** A projeção stock em Vulkan divergiu em 1 323 das 2 880 saídas pré-bias do expert 28. Um shader do Tesy que executa a soma na ordem do operador CPU reproduziu todas as palavras F32. Os dois shaders consumiram a mesma preparação da ativação, os mesmos 4 406 400 B da matriz MXFP4 original e o mesmo slot. O executável, o dispositivo, o dispatcher e o controlo negativo foram os mesmos. A observação é da camada 0, primeiro decode na posição 189. [Referência do grafo CPU](../cpu/README.md) · [Reconstrução aritmética independente](../reference/README.md) · [Ensaio stock e falha de instrumento preservada](../radv/README.md)

| Cálculo | F32 diferentes do grafo CPU | Maior diferença absoluta | Maior distância ULP | Controlo de slot |
|---|---:|---:|---:|---|
| Operador CPU, um rank isolado | 0/2 880 | 0 | 0 | Gold verificado contra o grafo de quatro ranks |
| Vulkan C269, redução em subgroup | 1 323/2 880 | 2⁻²² | 1 024 | 2 880 zeros |
| Vulkan Tesy, redução na ordem AVX2 | 0/2 880 | 0 | 0 | 2 880 zeros |

No controlo stock a primeira diferença aparece na saída 2. As 90 escalas e os 2 880 códigos do operando coincidem com a CPU. Recalcular os 2 880 produtos com esse operando e a ordem CPU confirma que a discrepância está a jusante da preparação da ativação. O kernel Tesy conserva duas sequências de 45 blocos, oito somas inteiras parciais por bloco e a árvore final de somas F32. O compilado contém duas instruções Fma, 21 decorações NoContraction e uma barreira de workgroup. A prova numérica é específica desta entrada e dispositivo. [Shader Tesy](gate.comp) · [Regras de avaliação em Vulkan](https://github.khronos.org/Vulkan-Site/spec/latest/appendices/spirvenv.html)

**Decisão.** NO_GO para substituir este gate pelo shader stock sob o contrato bitwise. GO para a composição do rank com o kernel ordenado. O processo do ensaio Tesy demorou 64,760 ms com quantização, duas projeções, fences e supervisão; o pico no scope foi 24 985 600 B, teto 128 MiB sem swap. O custo de um kernel isolado, o serviço do FFN e o impacto na conversa continuam desconhecidos. O ensaio leu o peso real do pack colocado no NVMe e colocou-o num buffer importado de quatro slots densos. O mapa do manager usa um stride de 13 221 888 B por slot para três matrizes. Importar essas vistas, preservar a geração até à última leitura e medir a redução dos quatro ranks são condições de progressão.

### Reprodução

Usar uma checkout limpa de fe7aaac5, a árvore stock R02 a2b4125e e as pastas privadas verificadas nas partes 83–85. O verificador autentica ambos os percursos CPU e o executável Vulkan. O filho vê apenas a ativação real, os módulos, o pack e as saídas que vai escrever. Usar diretórios novos em cada execução. A preparação do stock e da referência está documentada nos braços correspondentes. [Protocolo](protocol.md) · [Recibo físico](receipt.json) · [Arquivo CPU](../../../private_archive/part-83.json) · [Arquivo stock](../../../private_archive/part-84.json) · [Arquivo Tesy](../../../private_archive/part-85.json)

```sh
D=research/qualification-retake/igpu_resident_rank/projection/ordered_dot
python3 -IB "$D/build.py" --new-output-dir "$ORDERED_BUILD"
python3 -IB "$D/run.py" \
  --stock-checkout "$STOCK_CHECKOUT" --build-dir "$STOCK_BUILD" \
  --build-sha256 65a34219018b3e856ed18bebf9d3fe03b0ec5a8d5ed9cfd0b28bc50fc615d58e \
  --stock-dir "$STOCK_RUN" --stock-sha256 b8316f5859bc4573acbdb26644a64d2e41a3f1085b35a8ef7e9680f679bf1fb8 \
  --ordered-dir "$ORDERED_BUILD" --ordered-sha256 9a6b01afd0a80b8c5f7096de5806642e601ad5cfe3d698d675d3899590bbf9c3 \
  --cpu-dir "$CPU_RUN" --cpu-sha256 34f504b177c8878290513a8aa45d725cf54eae5915ba9f351579f503b5dd2ca7 \
  --arithmetic-dir "$ARITHMETIC_RUN" --arithmetic-sha256 77af85bff7e65de6c084268da4f665c2cb01e56df61e00084692b98b153d8cc1 \
  --reference-dir "$REFERENCE_74" --pack "$PACK" --new-output-dir "$ORDERED_RUN"
```
