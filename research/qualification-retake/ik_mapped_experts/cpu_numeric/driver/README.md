# Cliente ik com 16 posições e um teacher

**PASS sintético em R03.** O cliente usa a API de carregamento de produção do ik e duas chamadas a `llama_decode`. D0 e D1 mapearam seis matrizes MXFP4 e seis biases F32 diretamente do mesmo GGUF de 3 390 592 bytes. O contexto teve 8192 posições, KV F16 integral, batch 256, microbatch 32 e oito threads em cada tipo de cálculo. Após cada chamada o KV da sequência zero tinha 16 e 17 células usadas, respetivamente. D0 abriu zero workers de prefetch e D1 abriu quatro. Ambos desativaram o pool antes de libertar o modelo. [Contrato](protocol.md)

| Posição | F32 comparados D0/D1 | SHA-256 das duas saídas | Argmax único |
|---|---:|---|---:|
| 15 | 32/32 idênticos | `25321381d0fc2414cec11f9f9c703ff34d720cf025c352ebb1bdab862f2bbe48` | 6 |
| 16 | 32/32 idênticos | `ef393e635f83722a874838edb86808bb3f696cfa98880b12ebb17e4de803a911` | 23 |

A calibração sintética usa o mesmo programa e fornece o controlo local da primeira linha. O teacher sintético pré-fixado 6 coincidiu com o primeiro máximo. O C110 real tem teacher 976 e primeiro máximo de referência 3659. A autorização da segunda chamada requer máximo único de 3659 e toda a primeira linha finita. D1 compara também os bytes da sua primeira linha com o D0 antes da segunda chamada. Os três controlos de corrupção ou máximo errado produziram os códigos 42 e 43 antes do teacher e 44 depois de guardar a segunda linha. As assinaturas dos ficheiros e o máximo são verificados também em Python. O teste confirma o cliente e o efeito numérico do prefetch nesta fixture. O estado do smoke 120B nesta unidade é **NOT_RUN**.

A família sintética utilizou 61 739 008 bytes no pico do cgroup (cap de 268 435 456 bytes). `memory.swap.peak`, `oom`, `oom_kill` e `max` ficaram a zero e o scope terminou `inactive/dead`. O pico RSS individual de D0 foi 51 964 KiB e o de D1 51 356 KiB. As marcas nativas usam `CLOCK_MONOTONIC` para carga, contexto, prefill, teacher e cleanup, incluindo sincronização no fim de cada decode. O máximo de espaço virtual de 1 GiB aplica-se apenas a esta fixture sintética. O smoke real requer um envelope físico separado que permita o mapeamento virtual integral.

## Identidades e reprodução

O build R03 tem SHA `c8ff04f94d867ab8447598750ada85891fa767e9ebebe863e8b1833d50e7393f`; ELF `fff88998c3743a1a7d473d256c3ea3b33e89180e5a90e2ca290d361f3d120ebd`; recibo sintético `caba065a2dfa9e8859f8000e804362387b2483de7ba266333be3d56f021b924b`. Usar o código do commit `69c8f938`, os objetos R03 CPU do ik `7a5d90009b7ae55d3239cdd33244977c4eb10ff6` e o diretório privado de tiny_loader R02 com recibo `b10222365dec972020668e3e9a9874018f8af2a7170ddef2c9f97ff60018cd92`. O build regista os caminhos, a árvore do projeto e os SHA das bibliotecas, ELF e compiler. A auditoria usa o loader com `--list`, `ldd -r`, `dladdr`, as VMAs dos tensores e os eventos reais de `mmap` e `madvise`.

Executar na pasta do cliente. `IK`, `OBJ` e `TINY` designam a fonte, os objetos e o diretório tiny_loader verificados. Usar `BUILD` e `RAW` novos, um `SCOPE` exclusivo com prefixo `tesy-ik-numeric-` e `BUILD_SHA` calculado sobre o recibo produzido.

```sh
python3 -IB run.py build --source "$IK" --objects "$OBJ" --new-output-dir "$BUILD"
systemd-run --user --scope --quiet --unit="$SCOPE" -p MemoryMax=256M -p MemorySwapMax=0 \
  python3 -IB run.py synthetic --build "$BUILD" --build-sha256 "$BUILD_SHA" \
    --tiny-dir "$TINY" --objects "$OBJ" --scope "$SCOPE" --new-output-dir "$RAW"
```

O cliente entrega ao supervisor do smoke `ik-cpu-numeric c110 D0|D1 MODEL IDS17.I32 3659 NEW_OUTPUT_DIR [D0_RAW_DIR]`. O último parâmetro é obrigatório exclusivamente em D1. O supervisor deve autenticar o modelo e os IDs, o ELF e os dois providers e, em D1, o recibo e os dois ficheiros de referência `pos15.f32` e `pos16.f32` de D0. Cada posição real ocupa 804 352 bytes. A comparação com C110 e com a referência stock pertence à revisão externa de cada posição e pressupõe a mesma sequência de entradas. O perfil de colocação física e a alocação SWA de cada referência limitam essa comparação.

Os dois FAIL anteriores ficaram preservados. R01 parou antes do primeiro decode no teste da capacidade de KV. R02 produziu as duas rows da calibração e parou na verificação do provider antes de iniciar D0. [Correção da capacidade](r02.md) · [Correção da identidade ELF](r03.md)
