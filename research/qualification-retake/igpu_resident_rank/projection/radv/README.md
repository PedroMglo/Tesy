# A projeção gate MXFP4 de e28 na Radeon

**NO_GO para substituir a projeção pré-bias da CPU por este shader MMVQ sob igualdade bit a bit.** Na entrada real da posição 189, o shader C269 produziu 2 880 valores F32 finitos. Divergiram **1 323**, incluindo a linha 2, onde a palavra CPU `3e92037b` passou a `3e92037c` na Radeon. As 90 escalas F16 e os 2 880 códigos i8 da ativação coincidiram integralmente. O ramo alternativo que consulta o slot 2 zerado produziu 2 880 zeros. [Recibo medido](evidence/receipt.json) · [Protocolo congelado](protocol.md)

| Observação | Resultado |
|---|---:|
| F32 exatamente iguais na linha completa | 1 557 / 2 880 |
| F32 a até 1 ULP da CPU | 2 420 / 2 880 |
| Maior diferença absoluta | 2⁻²², na linha 1 807 |
| Maior distância em ULP | 1 024, na linha 2 000 |
| Diferença absoluta nessa linha 2 000 | 2⁻²⁵, para um valor CPU de 0,000377819 |
| Q8_1 × Q8_0, escala e códigos usados pelo dot | 90 / 90 escalas e 2 880 / 2 880 códigos iguais |

**O que executou.** O supervisor autenticou o grafo CPU que recebeu a linha `attn_post_norm` deste pedido e confirmou que a imagem obtida pelo rank isolado e a capturada no grafo de quatro ranks são idênticas. Uma abertura do pack original forneceu apenas os 4 406 400 B da matriz gate de e28 pelo offset 371 245 056. O shader recebeu a mesma linha F32 das fontes C127/C270 e sem acesso ao gold CPU. O buffer importado conservou o stride real de uma matriz e a posição de e28 no slot 3, à distância de 13 219 200 B da base. A fixture materializou os primeiros quatro slots e manteve vivos os buffers até ao último leitor. [Entrada e colocação](../input.md) · [Referência física](../cpu/README.md)

O shaderc local passou o teste de compilação de integer-dot do C269. A Radeon 890M anunciou aceleração de packed signed 4×i8, operações aritméticas em subgroup e suporte a exigir 64 lanes. A seleção manual reproduziu o ramo C269 MXFP4 × Q8_1 para M=K=2880, uma posição. A fixture lançou o `quantize_q8_1_x4_subgroup` do pin e, depois da barreira, o `mul_mat_vec_id_mxfp4_q8_1_f32_subgroup_no_shmem`. Seis SSBO, push constants de 48 B, especializações de 64 lanes e duas linhas por grupo, 1 440 grupos em x, um em y para o rank 0 e um em z. O ID veio de um buffer I32, com 3 no ensaio e 2 na contraprova. O SHA-256 do SPIR-V MMVQ é `844058d5a5c41ea251cd3721e77878036a0d34e8d8a2db8fe64a8e34864cffba`. O dispatch automático num servidor GGML Vulkan continua por observar. [Compilação dos fontes pinados](compile.py) · [Descritores e lançamento](projection.inc)

A diferença já ocorre com a mesma ativação quantizada e os mesmos bytes de peso. Isto localiza a fronteira a investigar no cálculo do produto e na acumulação/redução das contribuições. A leitura da saída completa não revela qual acumulação parcial divergiu primeiro. Uma alternativa que reproduza as lanes, FMA e soma horizontal da CPU pode reaproveitar o mesmo controlo e a mesma entrada. A decisão refere-se à exatidão desta projeção. Não se mediram logits, qualidade, redução de latência do cliente ou adoção de um FFN completo. [Reconstrução dos bytes da referência](../reference/protocol.md)

## Proveniência, limites e reprodução

| Identidade | Build | Ensaio |
|---|---|---|
| R01, commit `139b6772` | `1b796c4c276ce7e6322ae46105c2051d9cc82c0daf9e5c4bb91073f002661deb` | `dc7e21f69375e102fa6d962a094994afd0f5e67201fec7a040e24d08918d9c93`, FAIL preservado |
| R02, commit `a2b4125e` | `65a34219018b3e856ed18bebf9d3fe03b0ec5a8d5ed9cfd0b28bc50fc615d58e` | `b8316f5859bc4573acbdb26644a64d2e41a3f1085b35a8ef7e9680f679bf1fb8`, medido |

Na R01 a verificação de procedência de SHA256 parou antes da leitura da matriz e da primeira projeção. O ELF passou a `dladdr` o endereço do seu trampolim PLT 0x400850. Na R02, `dlopen` abriu o caminho de libcrypto autenticado, `dlsym` encontrou a função, `dladdr` confirmou a biblioteca e esse mesmo ponteiro calculou o SHA da matriz. As duas revisões produziram shaders idênticos. O resultado da R02 ocupou 115,3 ms desde o lançamento do supervisor systemd até ao retorno do filho, com pico de 30 498 816 B dentro do limite de 128 MiB, swap proibido e scope inativo no fim. Esse intervalo inclui inicialização, três despachos, fences, autenticação e cleanup. Nenhum forward do 120B. Os headers Khronos 1.3.204, necessários para consultar as propriedades de integer-dot, foram usados de forma privada no build. [Commit dos headers](https://github.com/KhronosGroup/Vulkan-Headers/tree/1dace16d8044758d32736eb59802d171970e9448)

```sh
d=research/qualification-retake/igpu_resident_rank/projection/radv
python3 -IB "$d/test_run.py"
python3 -IB "$d/build.py" --backend "$C269" --headers "$KHRONOS_INCLUDE" --new-output-dir "$NEW_BUILD"
python3 -IB "$d/run.py" --build-dir "$NEW_BUILD" --build-sha256 "$BUILD_RECEIPT_SHA" \
  --cpu-dir "$CPU_PROJECTION" --cpu-sha256 "$CPU_RECEIPT_SHA" \
  --reference-dir "$PART74" --pack "$C290_PACK" --new-output-dir "$NEW_RUN"
```
