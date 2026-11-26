# Uma posição versus três no MUL_MAT_ID CPU

**O mesmo operador C269 produziu os mesmos 69 120 padrões F32 ao avaliar as posições uma a uma ou em conjunto.** A igualdade inclui todos os quatro ranks da primeira posição em ambas as formas de ativação. Os bytes Q8_0 que o operador deixou no workspace também coincidiram. O resultado delimita duas entradas sintéticas no Ryzen AI 9 HX 370. A divergência dos logits e do KV observada com o modelo completo continua sem uma causa localizada. [Recibo da fixture](receipt.json) · [Medição do KV](../kv_difference/README.md)

| RHS F32 | F32 diferentes nas três posições | F32 diferentes na primeira posição | Bytes Q8_0 diferentes | F32 diferentes com um ID trocado |
|---|---:|---:|---:|---:|
| [2880,1,T], partilhado pelos quatro ranks de gate/up | 0 / 34 560 | 0 / 11 520 | 0 / 9 180 | 2 880 / 2 880 do rank escolhido |
| [2880,4,T], independente por rank como no down | 0 / 34 560 | 0 / 11 520 | 0 / 36 720 | 2 880 / 2 880 do rank escolhido |

A fixture executou 12 grafos de um nó. Em cada forma de RHS, fez três chamadas T=1 e uma T=3 para o contraste. Executou mais duas chamadas T=3 para os controlos. A permutação nativa 2,0,1 deslocou os três blocos de outputs e de operandos quantizados exatamente para as posições esperadas. A troca de expert físico 3 por 5 no primeiro rank na primeira posição manteve o Q8_0 e os onze outros vetores F32. As posições cobriram sete experts com reutilização entre posições e doze linhas de saída distintas por forma. Usaram o mesmo buffer CPU normal de 40 slots e a mesma equipa configurada de oito threads. A preparação gerou um tensor de pesos e duas famílias de ativação; cada forma representa uma projeção isolada. [Entradas e controlos congelados](protocol.md) · [Execução do operador](fixture.cpp)

### Onde a geometria entra no C269

No pin `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`, `src/llama-moe-stream.cpp:165` cria o cache contíguo das matrizes usando o tipo de buffer da camada; a fixture real CPU0 usa `ggml_backend_cpu_buffer_type()`. Em `ggml/src/ggml-cpu/ggml-cpu.c:1722`, GGML oferece o nó às implementações de buffers adicionais antes do dispatch normal. O caminho de repacking para MUL_MAT_ID em `ggml/src/ggml-cpu/repack.cpp:4791` requer que o peso esteja no buffer próprio de repacking. Nesta execução, a identidade do buffer do peso era a do CPU normal e o ponteiro de metadados adicionais era nulo. [Consumidor CPU0 já qualificado](../../../packed_real_layer/layer.cpp)

A tabela de tipos do CPU em `ggml-cpu.c:280` seleciona MXFP4 × Q8_0 com uma linha por dot. Em `ggml-cpu.c:1528`, as oito threads repartem os 90 blocos de cada RHS entre si. A implementação x86 do conversor em `arch/x86/quants.c:302` quantiza blocos de 32 valores, incluindo a escala F16. Alterar o número de posições pode mudar o agrupamento dos ranks por expert e o tamanho dos chunks de linhas de saída. Em `ggml-cpu.c:1457`, cada destino continua a receber um dot de comprimento 2880 com `nrc=1`. O dot x86 do pin está em `arch/x86/quants.c:918`. O programa confirmou AVX2, os passos em bytes dos tensores, a origem das funções de conversão e de dot no DSO CPU selado e os bytes Q8_0 frente à conversão direta. [Hashes das fontes e validação](run.py)

O caso anterior de parking incluiu T=1 e T=3 com matrizes 64×16 e comparou políticas para cada geometria. A observação e28 comparou um e quatro ranks com uma posição. Nenhuma dessas duas medições fez o contraste desta tabela. Os inputs desta fixture permanecem distintos dos tensores do modelo; os resultados tampouco identificam atenção, outras projeções, vieses, intervenções de parking ou a primeira operação divergente no prefixo C127. [Fixture do parking](../../../parked_mmid/test_kernel_graph.cpp) · [Gold da projeção e28](../../../igpu_resident_rank/projection/reference/README.md)

### Reprodução e custo

O protocolo foi selado em `0853de24`. O build R01 em `220f120b` falhou no linker e preservou o recibo `8e8c5ea69ca1b6467d6ebbcf5fe83c891c13be37e1710973689ecb3d941d172a`. O header C269 declara `ggml_threadpool_get_n_threads` e o ELF selecionado não exporta esse símbolo. R02, em `e73f3cde`, verificou a configuração no parâmetro de construção, o mesmo ponteiro e oito threads em cada plano, além de uma equipa OpenMP de oito threads e modo dinâmico desligado. O novo build produziu o ELF SHA `c1fd3e88acbff21cce4ceeeb5c1c1fcc62a80c15519e74da43dcb9ba1dae8e55` e o recibo `7782679c24f4d79458e11fabb8c640c2307ad7ba65314139e9d68885445ade79`. O único processo nativo de medição foi lançado a partir desse ELF. [Código de verificação](run.py)

O build R02 demorou 0,772 s no verificador, com pico de cgroup de 154 365 952 B. A execução e a graduação demoraram 0,260 s no verificador, com pico de cgroup de 196 255 744 B, RSS máximo observado nos filhos de 181 720 KiB, zero swap e 2 165 411 B de dados privados anteriores ao recibo. O limite de memória foi de 256 MiB por scope. Esses relógios medem o custo de obter a evidência. [Recibo físico](receipt.json)

Na checkout limpa de `e73f3cde`, apontar `B` para o backend C269 e escolher dois destinos e nomes de unidade novos. A verificação exige os dois DSO CPU/base publicados, Python 3, o compilador C++17, OpenMP e libcrypto locais.

```bash
P=research/qualification-retake/history_lookup/b3_numeric/cpu_row_geometry
COMMIT=$(git rev-parse HEAD)
B=/mnt/sdisk-ssd-ext/Tesy/repo/c7-native-placement-screen-20260927-1117utc/backends/c269-layer-last-use
python3 -IB "$P/test_run.py"
systemd-run --user --scope --unit="$BUILD_UNIT" -p MemoryMax=256M -p MemoryHigh=256M \
  -p MemorySwapMax=0 timeout 60s python3 -IB "$P/run.py" build \
  --backend "$B" --commit "$COMMIT" --new-output-dir "$BUILD_DIR"
BUILD_SHA=$(sha256sum "$BUILD_DIR/receipt.json" | cut -d' ' -f1)
systemd-run --user --scope --unit="$MEASURE_UNIT" -p MemoryMax=256M -p MemoryHigh=256M \
  -p MemorySwapMax=0 timeout 60s python3 -IB "$P/run.py" run \
  --backend "$B" --commit "$COMMIT" --build-dir "$BUILD_DIR" \
  --build-sha256 "$BUILD_SHA" --new-output-dir "$PHYSICAL_DIR"
```

A parte 99 conserva 68 ficheiros e 2 218 691 bytes da falha de ligação R01, do build R02 e da execução física. A verificação reabriu o manifesto, o tamanho e o SHA-256 de cada ficheiro. [Recibo do arquivo privado](../../../private_archive/part-99.json)
