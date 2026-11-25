# Projeção gate de e28 no primeiro decode de CPU0

A posição absoluta 189 tem uma linha de entrada real disponível para comparar a aritmética da projeção. Nos índices C127 e C270, `decode0/0/attn_post_norm` tem 2 880 F32 finitos, SHA-256 `f4b7b1fc1595244c263e292a8cd2d6c1d3c939e00b56e151c5c5d48fc403092e`. Os ranks lógicos são 28, 24, 8 e 16. À multiplicação correspondem as slots 3, 14, 6 e 35; e28 ocupa a slot 3, geração 6. As sete linhas de cada índice conferem byte a byte com o bundle da parte 74. [Referência C127/C270](../../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/cpu_alias/manager/decode_reference/README.md) · [Recibo de entrada e hashes](input-receipt.json)

| Dado observado | Dimensões / bytes | Identidade |
|---|---:|---|
| Registo C290 de e28 no pack colocado | 13 258 752 B ao offset 371 245 056 | SHA `c7724c5468819bb25f15ccb437f5a2d681c1b1011fabb0eb9241d096d24145df` |
| `blk.0.ffn_gate_exps.weight`, expert 28 | 2 880 × 2 880 MXFP4, 4 406 400 B, offset relativo 0 | SHA `3a76d368a4c215dafd9d39e740d1db137709d8bac6df70084c918656ec31cc50` |
| `ffn_moe_out`, saída completa da camada | 2 880 F32, 11 520 B | SHA `6bc70d200ac08db00f6c3fa34098bd660d2ba4bc4c02368de319cbadf6167333` |
| `ffn_moe_gate`, rank 0 antes do bias | 2 880 F32 esperados | Ausente nos dois índices e na saída da fixture CPU0 |

A leitura do registo confirmou os seis hashes de componentes e incluiu o padding no hash integral. O digest integral do pack vem da colocação anterior. O capturador guarda os 128 logits do router, observa o consumidor do bias para atestar os bytes ligados e guarda a saída após as três projeções e a redução dos quatro ranks. O comparador residente C127 validou essa saída. O tensor intermédio antes do bias requer a sua própria referência. [Seleção de tensores](../../../../tools/c127_slots40_boundary_capture.cpp#L400) · [Comparador residente](../../../../tools/c7_layer_reference.cpp#L251) · [Fixture shape 1 já qualificada](../../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/cpu_alias/manager/real_layer/decode/README.md)

**Próximo gate.** O C269 original (`d0ebfbcc6c8f456bc1083027c1b08075a32824d8`) já executa esta operação no backend CPU da fixture. A chamada do fragmento `pairs` é `ggml_mul_mat_id(c, t[0], in3, physical)`, antes de `ggml_add_id(c, gate, t[3], logical)`. A observação mínima é ler o resultado imediatamente no retorno do callback de avaliação desse MUL_MAT_ID, identificando o peso gate original e a CPU. Para o rank 0, após verificar tipo F32, dimensões [2880,4,1,1], stride inicial 4 B e slots reais, a chamada é `ggml_backend_tensor_get(gate, out, 0, 2880*sizeof(float))`. Conservar o teste de igualdade integral do FFN e os providers CPU/base do recibo. A leitura ocorre antes da reutilização do buffer pelo scheduler. Uma execução isolada com apenas a matriz de e28 e ID físico 0 também é possível; reduzir quatro ranks a um e tornar o peso contíguo altera a geometria. Essa forma deve reproduzir a linha medida no grafo original antes de servir de referência para a iGPU. A referência de projeção, sua comparação com a iGPU e qualquer preço de serviço ficam pendentes. [Grafo executado e callback existente](../../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/cpu_alias/manager/real_layer/decode/decode.cpp#L280)

Para conferir o recibo, usar o bundle `tesy-cpu0-decode-reference-20261125-r01` na parte 74. No shell, com `BUNDLE` e `PACK` apontados aos originais:

```sh
sha256sum "$BUNDLE"/{plan.json,receipt.json,attn_post_norm.bin,ffn_moe_out.bin}
dd if="$PACK" iflag=skip_bytes,count_bytes skip=371245056 count=13258752 bs=1M status=none | sha256sum
```
