# Ativação do dot MXFP4 no C269

**O código CPU e a expressão GLSL podem produzir códigos i8 diferentes para o mesmo F32.** O verificador confere por SHA-256 dez ficheiros do pin C269 `d0ebfbcc6c8f456bc1083027c1b08075a32824d8` e calcula cada operação em binary32 com arredondamento ao mais próximo e desempate para o par. O recibo contém os bits de entrada, intermédios, escala binary16 e resultado. A execução do operador RADV continua por medir. [Verificador](check.py) · [Recibo reproduzido](receipt.json)

Em `ggml/src/ggml-cpu/ggml-cpu.c:280–285,1502–1510,1545–1608,1657`, o expert físico seleciona os pesos por `cur_a*nb02`. A ativação F32 de cada projeção é convertida em Q8_0. Na linha K=2880 são 90 blocos de escala F16 e 32 i8, 3060 B. No ramo AVX2, `ggml-cpu/arch/x86/quants.c:302–346,918–964` quantiza a ativação, descodifica os nibbles MXFP4 por tabela, acumula produtos inteiros e aplica as escalas com FMA. Tanto no decode como na tile, conserva-se o contrato de redução de R0.

Para os exemplos use-se um bloco de 32 valores `(máximo,v,0,…)` e um peso MXFP4 que vale 1 apenas na coordenada de `v` (expoente 127, nibble 2). Os restantes blocos da linha podem ser zero.

| Ramo comparado com Q8_0 | Máximo e dois valores de v | Resultado do CPU nos dois blocos | Resultado da expressão alternativa |
|---|---|---|---|
| RHS float | 1, com 0 e 2⁻¹⁰ | 0 e 0 | 0 e 2⁻¹⁰, ambos exatos também em F16 |
| RHS Q8_1 | 11, com F32(33/254) e 3/16 | códigos 2 e 2 | códigos 1 e 2 |

O primeiro valor do segundo par tem bits `3e050a14`. O CPU usa `127/max` e obtém `3fc00000` (1,5) antes do arredondamento inteiro. A sequência GLSL usa `1/(max/127)` e obtém `3fbfffff` (1,4999998807907104). O segundo valor controla a escala comum `2d8b` em F16. Para MXFP4, tanto o produto vetorial como o matricial usam apenas a escala `ds.x` do bloco Q8_1. Ver `ggml-vulkan/vulkan-shaders/{quantize_q8_1.comp:80–87,mul_mat_vecq_funcs.glsl:115–132,mul_mmq_funcs.glsl:147–183}`, sob `ggml/src/`.

### Pipeline a identificar no dispositivo

- Em `ggml-vulkan.cpp:10087–10104`, MUL_MAT_ID MXFP4 usa matvec-ID até 8 posições, incluindo decode e a tile de 5. Com 20/32 usa matmat-ID. O integer-dot depende do suporte do build, da propriedade do dispositivo para dot i8 packed acelerado, do F32 contíguo com a dimensão requerida divisível por quatro e da existência do pipeline. A heurística AMD de matvec aceita MXFP4 com K=2880 por omissão. O fallback vetorial usa RHS F32. No matricial, layout e coopmat2 podem exigir staging em F16. Condições e overrides em `:5832,6020,6592–6596,8869–8917,9564–9616,9884–9909`.
- Nos dois ramos Q8_1, a conversão usa `quantize_q8_1_x4`, podendo reutilizar a ativação já convertida. O gerador fixa `QBLOCK_X4=1` e acrescenta `USE_SUBGROUPS=1` quando o runtime seleciona a variante com `subgroup_clustered && subgroup_require_full_support`. A alternativa usa memória partilhada. A espec. 0 recebe `device->subgroup_size`. Dois storage buffers e os push constants `ne,num_blocks` definem esta passagem. Cada grupo de quatro blocos guarda quatro pares escala/soma F16 e 128 códigos i8. Ver `vulkan-shaders-gen.cpp:845–849`, `types.glsl:231–235` e `ggml-vulkan.cpp:5083–5087,8557–8583,9812,10013`. O passo consumidor é gerado por `mul_mat_vecq.comp` para o dot vetorial ou `mul_mmq.comp` para o matricial (`vulkan-shaders-gen.cpp:615–617,746–748`).

**Observação decisiva.** Um despacho isolado da variante x4 correta pode ler de volta o byte de `v` e a escala. No segundo exemplo, códigos 2 e 2 com a escala esperada refutariam a previsão 1 e 2 **naquele binário e dispositivo**. Devem registar-se o SPIR-V, os defines, a especialização, o driver e os bytes. Para extrapolar ao operador, é preciso testemunhar a seleção automática no grafo e comparar os F32 por rank. Em seguida há gold de decode C270 e de prefill C266 para o FFN. Só a conversa integrada pode estabelecer 6 tok/s e primeiro conteúdo final até 10 s, incluindo o efeito combinado com o pack. [Gate de memória anterior](../README.md)

Para reproduzir, a partir desta pasta, apontar `C269` ao backend local e conferir o recibo integral.

```sh
python3 -IB check.py --backend "$C269" | cmp - receipt.json
```
