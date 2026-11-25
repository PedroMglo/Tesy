# A decomposição do router em três produtos recupera os bits AR na camada 0

O mesmo peso F32 do router e as três entradas reais da camada 0 reproduziram **os dois resultados do 120B**. Com as três posições no mesmo grafo, substituir apenas o produto de largura três por três produtos de largura um e concatenar as saídas recuperou **384/384 logits, 384/384 scores com bias, 12/12 IDs ordenados e 12/12 pesos** de AR. O bias, a seleção top-4 e o softmax continuaram a ser aplicados às três posições em conjunto. [Recibo](receipt.json) · [Protocolo](protocol.md)

| Grafo GGML CPU | Referência do 120B | Logits diferentes / 384 | Scores com bias diferentes / 384 | IDs / pesos diferentes, em 12 | Chamadas SGEMM aceites / recusadas | Dots F32 de 2 880 valores |
|---|---|---:|---:|---:|---:|---:|
| Três chamadas individuais | AR | 0 | 0 | 0 / 0 | 0 / 24 | 384 |
| Um produto de três posições | B3 | 0 | 0 | 0 / 0 | 8 / 0 | 0 |
| Três produtos individuais e CONCAT num grafo | AR | 0 | 0 | 0 / 0 | 0 / 24 | 384 |

As oito chamadas aceites em B3 correspondem à entrada das threads na implementação do mesmo produto. Cada chamada AR individual teve oito recusas de SGEMM e 128 dots F32. O pin C269 em ggml-cpu.c:1299 oferece o produto contíguo a llamafile_sgemm. Em llamafile/sgemm.cpp:3708 o ramo x86 recusa uma única coluna. A tabela de tipos F32 em ggml-cpu.c:215 e o fallback em ggml_compute_forward_mul_mat_one_chunk usam ggml_vec_dot_f32. O executável contado encaminhou as chamadas para as funções do DSO qualificado; as 24 saídas binárias coincidiram com as do executável direto. A troca das duas primeiras linhas de pesos trocou exatamente os dois logits correspondentes nas três posições e preservou os outros 378. [Grafo e contadores](fixture.cpp) · [Validação](run.py)

A execução do 120B registou a atribuição da camada 0 à CPU. O dispatch acima foi contado na fixture, que reproduziu bit a bit os dois resultados reais nos seus próprios controlos. A diferença no router precede as diferenças no residual e no KV identificadas na família de referência. A restauração da camada 0 permite testar esta alteração estreita no grafo para as demais camadas. O efeito sobre a trajetória após a camada 0, a paridade final dos logits/KV e o throughput continuam por medir. [Primeira fronteira física](../README.md)

## Custos e reprodução

Revisão e4bb394b542620b9cdddd82f4a8db1f20c78eb3a, toolchain e DSOs pinados em run.py. O build dos dois executáveis demorou 1,132 s, pico do cgroup 153 772 032 B. A execução e validação demoraram 0,0562 s, pico 31 088 640 B. Estes valores são custos de qualificação. Os dois scopes tinham cap 256 MiB e swap zero. A fixture abriu só o peso de 1 474 560 B e o bias de 512 B da preparação pré-existente da camada 0, além dos ficheiros de referência e atribuição da parte 102. A GPU e o GGUF ficaram fora da execução.

```sh
u=research/qualification-retake/history_lookup/b3_numeric/first_boundary/router_row
commit=e4bb394b542620b9cdddd82f4a8db1f20c78eb3a
python3 -IB "$u/test_run.py"
systemd-run --user --scope --unit="$BUILD_UNIT" -p MemoryMax=256M -p MemoryHigh=256M \
  -p MemorySwapMax=0 timeout 120s python3 -IB "$u/run.py" build --backend "$C269" \
  --commit "$commit" --new-output-dir "$BUILD"
systemd-run --user --scope --unit="$RUN_UNIT" -p MemoryMax=256M -p MemoryHigh=256M \
  -p MemorySwapMax=0 timeout 120s python3 -IB "$u/run.py" run --backend "$C269" \
  --commit "$commit" --build-dir "$BUILD" --build-sha256 "$BUILD_SHA" \
  --family "$PART102/tesy-b3-first-boundary-physical-20261125-r01" \
  --weights-dir "$CPU0_PREPARED" --new-output-dir "$FRESH"
```

Na execução publicada, o recibo de build teve SHA-256 f75b5212032e6ff4a9218f17cb05be882034f4a9796d99cee11c9556cbe1876b e o recibo físico c4b9ae1d68613cf99ca5953f42718582e917a325611cb4f7ce7178a818eba4a5. A família AR/B3 que fornece as referências permanece na parte 102, manifesto 8baed0c5fe6f89d234107cf40e84fcb25bb2f77a7a682e3fac69be04bb7d7dfd.
