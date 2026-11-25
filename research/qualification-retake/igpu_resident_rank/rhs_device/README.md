# O shader Q8_1 na Radeon reproduziu os dois códigos da CPU

**GO para comparar uma projeção real.** O dispatch na Radeon 890M produziu os códigos **2 e 2**, ambos com escala F16 `2d8b`. A previsão 1 e 2 da expressão GLSL avaliada operação a operação ficou refutada neste binário. Os 3 312 bytes do formato Q8_1 x4 coincidem com a imagem construída a partir dos códigos e escalas previstos para o CPU, incluindo somas e padding próprios do Q8_1. [Recibo físico](evidence/receipt.json) · [Contrato prévio](protocol.md) · [Oráculo independente](../rhs/README.md)

| Bloco (30 posições finais zero) | CPU previsto | GLSL literal | RADV medido | Escala / soma F16 gravadas |
|---|---:|---:|---:|---|
| 11 e F32 de bits 3e050a14 | 2 | 1 | 2 | 2d8b / 4996 |
| 11 e 3/16 | 2 | 2 | 2 | 2d8b / 4996 |
| 127 e −3 | −3 | −3 | −3 | 3c00 / 57c0 |

A revisão independente dos bytes encontrou duas diferenças face à imagem literal. O offset 17 contém o i8 discriminante. O offset 2 pertence à representação F16 da soma escalada, `4996` medida e `498b` prevista. Os blocos zero e os dois de padding foram verificados. A escala e os códigos de cada bloco podem comparar-se com Q8_0. A soma adicional só integra o formato Q8_1. [Gerador e leitor](oracle.py) · [Contraprovas](test_oracle.py)

**Origem da diferença.** O módulo SPIR-V presente no build já contém a transformação. O máximo do bloco é o resultado %283. A instrução FDiv na palavra 625 calcula 127 / %283 e a seleção Phi envia esse valor à multiplicação das ativações antes do Round. É o mesmo quociente que o oráculo de fonte x86 usa para formar os códigos. A escala de saída é calculada por FMul do máximo com F32(1/127). Esta inspeção mantém aberta a igualdade das escalas para outras entradas e da acumulação do dot. [Revisor do SPIR-V executado](review_spirv.py)

**MEDIDO no portátil.** Com o commit limpo `aa52ae7d6bde1dd3486676ac1334d675947e1210`, o shaderc do sistema compilou o fonte C269 com Vulkan 1.2 e otimização de desempenho. A Radeon anunciou operações clustered em compute e computeFullSubgroups. A fixture selecionou pelo predicado C269 a variante QBLOCK_X4 + USE_SUBGROUPS, especialização 0 igual a 64, 12 grupos e push constants (2880,12). Módulo selecionado SHA-256 `a988ec4090dca42f89a13de2ce43a69c376a0e79919e6f56875d4b1e0ab1ad25`. Foram importadas duas alocações coerentes de 65 536 B. O intervalo submit→fence observado foi 1,070 ms e o invólucro de execução durou 63,925 ms. Trata-se de uma observação de um dispatch com o fence no host. O pico do scope foi 6 676 480 B, cap 128 MiB e swap desativado. O scope encerrou inativo, sem servidor ou forward. [Compilador](compile_shader.py) · [Supervisor](run.py)

O próximo teste pode usar a ativação/bits reais da primeira projeção do expert e28 na CPU0. Deve observar qual caminho o MUL_MAT_ID do GGML seleciona nessa chamada e comparar os F32 da projeção completa com a referência CPU. O dispatch independente qualificou a conversão nos dois blocos e o controlo. Os logits, a latência de cliente e o ganho combinado com o pack continuam por medir para esta arquitetura.

## Reprodução

Os testes do oráculo e do journal correm sem GPU. A referência independente do shader e os dois módulos compilados são específicos dos pins. Ambos os destinos de build e execução têm de ser novos.

```sh
d=research/qualification-retake/igpu_resident_rank/rhs_device
python3 -IB "$d/test_oracle.py"
python3 -IB "$d/test_run.py"
python3 -IB "$d/run.py" --build --headers "$KHRONOS_INCLUDE" --backend "$C269" --new-output-dir "$NEW_BUILD"
python3 -IB "$d/run.py" --build-dir "$NEW_BUILD" --build-sha256 "$BUILD_RECEIPT_SHA" --new-output-dir "$NEW_RUN"
python3 -IB "$d/review_spirv.py" "$NEW_BUILD/subgroup.spv"
```

Build R01 `8a3171e81809f8a1b151c3a3f5ad025320e91a67a283ae6eb52880ad8c728e75`. Execução R01 `472fa699385b57fc56df08c48264f0bb39ba8731365c3adc6b581858e2e45edd`. Saída `b2ce0eebb92489cdae2b5d5cdd4d4792ee7207bf748e955c1f5ee67d8102c434`. Uma compilação e uma execução confirmatórias concluídas à primeira tentativa. [Manifesto privado da parte 82](../../private_archive/part-82.json)

Para a comparação seguinte estão autenticados os 2 880 F32 de entrada e os pesos do expert 28 no primeiro decode de CPU0. A captura mede o FFN completo. A observação mínima que falta é a saída gate do rank 0 no grafo original de quatro ranks, antes do bias. [Entrada real, registo e observação](../projection/input.md)
