# Três sequências de tokens produzem a mesma resposta SSE de C281

**Os 47 IDs do segundo turno natural são ambíguos no registo do cliente.** Três sequências distintas reproduziram no parser e serializador originais de C281 os mesmos 40 eventos de escolhas e usage. Partilham as primeiras 46 posições e terminam em três IDs EOG diferentes. Isto prova a não unicidade da observação. O sampler real escolheu apenas uma trajetória. A economia de chamadas da cópia B3 no pedido real continua **INCONCLUSIVE**. [Pré-registo](protocol.md) · [Recibo](evidence/receipt.json)

## O que o cliente recebeu

O T2 de C281 reutilizou 2 044 IDs e processou mais 153. O servidor registou 47 saídas e terminou por EOS. O ficheiro do cliente contém 81 fragmentos de transporte e 40 objetos JSON. Destes, um anunciou o papel, 35 trouxeram raciocínio (162 bytes ASCII), dois trouxeram conteúdo final (5 bytes ASCII), um terminou a escolha e um comunicou o uso. O cliente pediu zero probabilidades. O único campo de IDs de saída apareceu vazio no bloco final de diagnóstico. Os raws C135/C136 guardam a mensagem agregada por canal e a contagem de 47 saídas. O trace de experts C135 identifica call, posição, camada, expert, slot e geração. Faltam-lhe os IDs dos tokens amostrados. Em C242 o controlo nativo usa outra entrada em duas posições e termina após 39 IDs. [Conversa E20](../../nvme_conversation/README.md) · [Controlo C242](../causal_pair/README.md)

No backend `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`, `server-context.cpp:1862–1907,2084–2125,2134–2142` acumula peças, espera por UTF-8 completo e envia o texto novo. Em modo streaming o evento final zera a lista de IDs. `server-task.cpp:158–172,486–549,1126–1180` traduz a mensagem de chat em diferenças por campo. Uma amostra pode gerar nenhum ou vários deltas. O relógio de chegada de uma linha SSE não identifica o passo do sampler que produziu cada byte.

## Teste construtivo sem pesos

A fixture usou o vocabulário original autenticado com 201 088 tokens e zero tensores. O contexto da mensagem começa em `<|start|>assistant`. A fonte C269 cria a PEG GPT-OSS segundo ferramentas, esquema de resposta, continuação e formato de raciocínio. O cliente C281 usou `/v1/chat/completions` com as mensagens oficiais, sem ferramentas nem esquema de resposta. A geração greedy tinha raciocínio separado, gramática de sampling vazia e cinco IDs preservados. Verificámos que os cinco correspondem exatamente aos marcadores usados pelo parser. A fixture obtém a mesma produção sem ferramentas por um exemplar neutro, confere o prefixo de geração, o formato e os controlos; o texto do utilizador não parametriza as produções nesta configuração. A gramática de sampling e a PEG que interpreta a saída são independentes. [Cliente R0](../../../../tools/c2_server_run.py) · [Origem do vocabulário](../../aster_vocab/README.md) · [Fixture nativa](witness.cpp)

Cada testemunho usou `common_token_to_piece`, a validação UTF-8 e os dois `server_task_result_cmpl_{partial,final}` originais. O comparador confrontou a sequência inteira de `choices` e `usage`, incluindo índices, `finish_reason`, cache e contagens. A escolha entre os três EOG produz o mesmo envelope. Timestamps, identificadores de transporte e tempos do servidor permanecem os da observação histórica. O ramo alternativo `commentary` produziu zero candidatos nesta construção, que exige uma peça por elemento. Trajetórias com outros agrupamentos, múltiplos blocos ou controlos fragmentados continuam abertas. A enumeração de EOG é completa **condicionada às primeiras 46 posições construídas**. O recibo contém apenas contagens.

## Consequência para a regra causal N=2/M=2

A regra recebeu os 2 197 IDs de entrada oficiais e apenas a história confirmada ao propor. O primeiro ID vem do prefill. Os três finais compatíveis deram os mesmos resultados nas duas janelas. A razão admissível é `(0,85 × passos − chamadas AR) / chamadas B3`, supondo custo AR médio constante e custo zero de pesquisa, rejeição, rollback, cópia e coordenação.

| Janela após a âncora | AR ordinárias | Verificações B3 | IDs aceites/apresentados | Propostas completas | Chamadas poupadas | B3/AR máximo para +15% |
|---|---:|---:|---:|---:|---:|---:|
| Primeiros 32 passos | 19 | 7 | 6/14 | 3/7 | 6/32 | 1,171429 |
| Até ao EOG, 46 passos | 23 | 11 | 12/22 | 6/11 | 12/46 | 1,463636 |

Estas três observações compatíveis justificam conservar aberta a pergunta sobre B3. Seria necessário mostrar que as outras trajetórias admitidas pelo SSE têm os mesmos limites, ou observar as 47 amostras reais (188 B em i32), incluindo EOG, ligadas ao pedido e à fronteira 2044+153. Para atribuir segundos ao mecanismo seria depois necessário qualificar a exatidão e medir o custo B3 emparelhado, incluindo miss e rejeição; para o objetivo do cliente subsiste também o prefill. M3 PARTIAL e M4 NOT_MET.

## Proveniência e custo

Pré-registo `95cfd806b75718a9e36e4f86ba76ac4c265707f6`; medição `be802eef663d94c66eaea7ddf61d94fd878314fd`. GCC 16.2.1. O primeiro build parou na ligação por nomes de bibliotecas incorretos, antes de produzir o executável. O segundo apontou diretamente para os ELF autenticados e produziu 1 379 208 B, SHA-256 `04d15307c17914c6bedceb66c7f8039394d2afbaf7888a8430b4c1d420b50ab4`. O recibo verifica os headers por comparação com os blobs do pin, as sete bibliotecas de C281 e a resolução dinâmica. [Falha de ligação](evidence/build-r01.json) · [Build confirmado](evidence/build-r02.json)

Os scopes impuseram 512 MiB de RAM, swap zero e 120 s; a fixture não fez forward, leitura de pesos ou compute GPU. A compilação bem-sucedida levou 6,44 s e 382 292 KiB de RSS. Os replays R01/R03 levaram 1,06 s cada, 369 700/370 060 KiB de RSS, e emitiram os mesmos 1 870 B, SHA-256 `0f1cf0deb31cd220e13d219a0e521b0359d1e5daee4223ffe96cd7ea39af4fe0`. O controlador R02 foi impedido pelo sandbox de abrir o socket systemd e terminou antes da fixture. [R01](evidence/replay-r01.json) · [R02 preservado](evidence/replay-r02.json) · [R03](evidence/replay-r03.json)

```sh
# LIBS é build-c269-cuda/bin. SERVER_LIBS é o bin da persistent-server C276 de C281.
# Os hashes esperados de headers/ELF estão em evidence/build-r02.json.
u=research/qualification-retake/history_lookup/natural47
inc=()
for d in include ggml/include common vendor vendor/nlohmann tools/server tools/mtmd src vendor/cpp-httplib
do
    inc+=(-I "$C269/$d")
done
systemd-run --user --pipe --wait --unit="$NOVA_UNIDADE_BUILD" --working-directory="$PWD" \
    -p MemoryMax=512M -p MemorySwapMax=0 -p RuntimeMaxSec=120s \
    g++ -std=c++17 -O0 -g0 --param ggc-min-expand=8 --param ggc-min-heapsize=8192 \
    -MMD -MF "$NOVA_BUILD/headers.d" "${inc[@]}" "$u/witness.cpp" \
    -L "$SERVER_LIBS" -L "$LIBS" "-Wl,-rpath-link,$LIBS" "-Wl,-rpath-link,$SERVER_LIBS" \
    "$SERVER_LIBS/libllama-server-impl.so" "$LIBS/libllama-common.so" \
    "$LIBS/libllama.so" "$LIBS/libggml-base.so" -pthread -o "$NOVA_BUILD/witness"
systemd-run --user --pipe --wait --unit="$NOVA_UNIDADE" --working-directory="$PWD" \
    -p MemoryMax=512M -p MemorySwapMax=0 -p RuntimeMaxSec=120s \
    env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    CUDA_VISIBLE_DEVICES= LD_LIBRARY_PATH="$SERVER_LIBS:$LIBS" python3 -B "$u/screen.py" \
    --repo "$PWD" --natural-root "$C281_E20" --vocab-only "$VOCAB_ZERO_TENSORES" \
    --witness "$NOVA_BUILD/witness" --witness-sha256 "$SHA_DO_EXECUTAVEL" \
    --new-output-dir "$NOVA_SAIDA"
```
