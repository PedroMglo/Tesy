# Última projeção do expert 28, CPU0, posição 189

**GO para o down pré-bias deste rank.** A Radeon 890M recebeu a saída F32 da sua própria ativação, requantizou-a e leu a matriz down do primário CPU no slot 3. Coincidiram os 3 312 bytes do RHS Q8_1 com a captura anterior da Radeon e os 2 880 F32 do down com o grafo independente de quatro ranks na CPU. Mudar apenas o descritor para os pesos de e24 no slot 14 alterou todos os 2 880 F32. [Recibo medido](evidence/receipt.json) · [Protocolo congelado](protocol.md)

| Dado | SHA-256 |
|---|---|
| SwiGLU produzido na Radeon, entrada deste ensaio | `1fbf0b978b0a992526a0f13427ba86412569bff28f33429903b05e9d5cf2d8d3` |
| Q8_1 usado pelas duas projeções | `6215822f56ad6d4c855433a44997aa5802ce0f487c224e89b3607b31c8b1fcfa` |
| e28, slot 3, geração 6 | `6aa4579903ad1948d27a7eebb2f6795f99c0ea82caa150613514a4f5c216f9e0` |
| e24, slot 14, geração 6, com entrada de e28 | `3d688d3201fb26afcd263725892006e7c5924b2a9d0f1f5ca25fe8a534488f22` |

O F32 de ativação tinha 979 diferenças em relação à CPU. O contrato do down ficou satisfeito porque as escalas e códigos consumidos pelo produto sobreviveram à composição da ativação com a quantização neste caso. A contraprova mantém essa ativação e verifica a sensibilidade à seleção dos pesos. A referência natural CPU de e24 usa a ativação do próprio expert. O ensaio de e24 com a entrada de e28 apenas exige valores finitos e distingue o slot. [Prova da ativação](../rank_activation/README.md) · [Subgrafo CPU de referência](../rank_cpu/README.md)

O revisor independente aplicou bias, ponderou o rank e combinou as três contribuições CPU do mesmo corte. Coincidiram a contribuição e28 e a saída FFN de referência, 2 880/2 880 F32 em cada comparação. Trata-se de composição offline de etapas medidas separadamente. [Revisão conjunta](../rank_join/README.md)

**Recursos.** Dois SET de 4 406 400 B no primário GGML de 528 768 000 B virtuais. O dispositivo acedeu diretamente a duas janelas anónimas privadas de 4 411 392 e 4 407 296 B, com offsets de descritor de 2 496 e 832 B. Ambas as vistas sobreviveram até ao respetivo fence. O scope atingiu 71 290 880 B de pico com cap de 128 MiB, swap zero e encerrou inativo. O envelope de 165,132399 ms inclui arranque, verificação de pesos e cleanup. São três despachos de um processo isolado com preparação e ficheiros entre etapas. Estes dados não medem um pedido, a concorrência 3+1 ou a utilização de largura de banda da iGPU.

**Proveniência.** Pré-registo `945ad2d5`, implementação `63f295e2780ea2976d42eebc9b9905219231bae9`, build R01 `e7ba245f940a6b88f58bd89cbd2a201603831cd16141b509b9c8a8f0a86be3ab` e recibo físico R01 `d9fc9e22380bc42560fec18c066db4decd1a857c835a7b0a6ecfc98dbcf132d9`. O programa verificou os hashes dos pesos, dos golds, da ativação e dos módulos antes de qualificar a comparação. Os recibos de origem e todos os hashes de saída constam do recibo medido.

Para reproduzir no portátil a partir da revisão limpa, executar nesta unidade com destinos exclusivos:

```sh
python3 -IB test_run.py
python3 -IB build.py --backend "$C269" --headers "$VULKAN_INCLUDE" \
  --primary-build "$PRIMARY_BUILD_R01" --new-output-dir "$NEW_BUILD"
python3 -IB run.py --build-dir "$NEW_BUILD" --build-sha256 "$BUILD_RECEIPT_SHA256" \
  --cpu-dir "$RANK_CPU_R01" --primary-dir "$PRIMARY_GPU_R01" --swiglu-dir "$SWIGLU_GPU_R01" \
  --pack "$C290_FULL_PACK" --new-output-dir "$NEW_RUN"
```
