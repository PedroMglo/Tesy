# Páginas de experts no ik_llama.cpp

**GO para testar o scheduler.** Em duas execuções do worker upstream, selecionar os mesmos quatro IDs pediu 52 924 416 B de páginas distintas. Se o primeiro pedido da época abranger os tensores inteiros, os workers pedem 1 692 069 888 B e a seleção posterior acrescenta zero. A ordem inicial decide a cobertura. Esta diferença pode afetar a escolha de backend no prefill nominal, onde quatro tiles têm 32 posições. [Protocolo](protocol.md) · [Resultado compacto](result.json) · [Condições do loader e do scheduler](loader.md)

## O que se executou

No **scheduler CPU do fork**, executar as mesmas duas camadas sintéticas a 32 posições com o lookahead habitual consultou 495 616 B numa única split e 13 373 440 B quando cada camada ficou numa split própria. Com `GGML_MOE_PREFETCH_AHEAD=0`, a cobertura foi de 495 616 B em ambas as disposições. A 1, 5 e 20 posições, todos os braços ON usaram páginas seletivas. Por política, os 1 180 IDs e os 151 040 F32 coincidiram com o controlo OFF. No **cabeçalho real**, o loader reconheceu 61 073 326 080 B de pesos e bias diferíveis. No **frontend offline**, o fork reproduziu todos os IDs dos dois prompts e todos os deltas dos canais ao reapresentar a geração C281 já conhecida. [Scheduler e falha de admissão preservada](graph/README.md) · [Índice nativo dos 687 tensores](header_index/README.md) · [Frontend e controlos negativos](frontend/README.md)

O GGML do fork construiu tensores MXFP4 de forma `[2880,2880,128]` e stride de 4 406 400 B por expert, a partir dos offsets da camada 0 no inventário C283. O verificador conferiu as três matrizes e os três bias de cada uma das 36 camadas. Os quatro workers upstream processaram os pedidos reais do operador sobre três intervalos de endereços virtuais. O teste respondeu «frio» às consultas de residência, capturou as chamadas de população e confrontou cada offset, comprimento e multiplicidade com uma referência independente. Só a sonda de elegibilidade de uma página anónima usou o MADV_POPULATE_READ do kernel. O corpus é sintético e o teste fez zero leituras do GGUF, zero transferências CUDA e zero forwards. [Testemunho nativo](native.cpp) · [Verificador de origem](verify.py)

| Primeiro pedido da época | Pedidos POPULATE | Soma pedida, B | Páginas distintas, B |
|---|---:|---:|---:|
| Quatro IDs, três matrizes | 33 | 53 022 720 | 52 924 416 |
| Tensores inteiros, seguidos dos mesmos IDs | 807 | 1 695 363 072 | 1 692 069 888 |
| Quatro IDs, seguidos dos tensores inteiros | 33 | 53 022 720 | 52 924 416 |
| Up e gate separados no operador fundido | 22 | 35 348 480 | 35 282 944 |
| ID 3 duplicado, um sentinela e um índice fora dos 128 | 9 | 13 258 752 | 13 234 176 |

As quatro larguras 1/5/20/32 repetiram os mesmos quatro IDs 0, 1, 63 e 127. A API seletiva recebeu sempre o mesmo conjunto. O arredondamento dos chunks de 2 MiB a páginas de 4 KiB explica a diferença entre soma e união. Na mesma época, uma nova seleção foi suprimida; na época seguinte voltou a pedir as páginas. A ausência de mapping registrado e o hook numa lane diferente de zero foram controlos de zero emissões. O hook legado com o pool desligado emitiu nove sugestões WILLNEED por largura. Os 44 casos passaram duas vezes. A fixture chama diretamente os operadores e a API de prefetch. Para calcular tráfego físico ou latência é preciso identificar a divisão real do grafo, residência anterior, faults e transferência até ao consumidor. O T2 do próprio fork continua por executar.

O loader completo do fork também executou um GPT-OSS sintético de duas camadas, com atenção sliding e global, 8 experts e top-4. Nas duas reproduções, os três modos de carregamento usaram as 12 vistas mapeadas do ficheiro e devolveram os mesmos 32 logits F32. O carregamento diferido evitou o prefault integral. A primeira tentativa expôs uma reserva virtual de 203 440 584 B do scheduler e ficou arquivada. Mantendo o limite físico de 150 MiB e distinguindo-o do espaço virtual, os picos medidos foram 54 013 952 e 52 297 728 B nos dois ensaios completos. A reprodução sobre a cópia privada confirmou os seis forwards e os dois encerramentos sem swap. [Modelo reduzido e diferenças de recursos](tiny_loader/README.md) · [Arquivo do grafo, índices e execuções](../private_archive/part-127.json) · [Builds e replays do frontend](../private_archive/part-126.json)

## Preparação e reprodução

O protocolo é `5ee02f5f`, o testemunho `1f1c9667` e a revisão limpa de execução `159e08e3`. Duas compilações/execuções da fixture produziram o mesmo executável SHA-256 `5e9364c5b240ab76c7ff247ed80535e81b12feba4dda1b3ae5beff8ef288df6d` e o mesmo recibo `aa885f0dae39a3b1a9e1fed0bb22184d971e880cece2f151b03b27d9d53aa3f7`. Levaram 2,14/2,21 s com RSS máxima de 343 032/343 424 KiB incluindo o compilador. A execução nativa tem limite de 30 s e 3 GiB de memória virtual. A energia desta validação fica desconhecida.

No primeiro preparo, desativar IQK MUL_MAT impediu a compilação de `ggml.c`. O segundo gerou a biblioteca em 18,93 s com IQK MUL_MAT, mas desativar IQK FLASH_ATTENTION deixou dois símbolos por resolver. O terceiro construiu CPU GGML, llama e common com o conjunto IQK do pin em 223,12 s e dois jobs. O maior RSS de um processo na compilação foi 1 534 972 KiB. O diretório da terceira preparação ocupou cerca de 101 MiB. A biblioteca GGML validada tem SHA-256 `5395348a4bffef748be95e7657cbd25dd2ceaaa50f4f00e0f9d58dc742329c0c`. A configuração serve os testes de formato e do frontend. O custo de inferência com uma configuração de produto exige medição própria.

```sh
git -C "$IK" rev-parse HEAD
cmake -S "$IK" -B "$BUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS_RELEASE=-O1 -DCMAKE_CXX_FLAGS_RELEASE=-O1 -DBUILD_SHARED_LIBS=ON \
  -DGGML_NATIVE=ON -DGGML_CCACHE=OFF -DGGML_CUDA=OFF \
  -DGGML_IQK_MUL_MAT=ON -DGGML_IQK_FLASH_ATTENTION=ON \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=OFF
cmake --build "$BUILD" --parallel 2 --target common
python3 -IB verify.py --source "$IK" --build "$BUILD" \
  --library "$BUILD/ggml/src/libggml.so" --library-sha256 "$GGML_SHA256" \
  --inventory "$C283_METADATA" --new-output-dir "$NOVO"
```

O revisor exige o commit e a árvore exatos do fork publicados no protocolo. O SHA da biblioteca tem de provir do binário previamente selado para a execução. Uma compilação com outro toolchain requer a sua própria proveniência. O teste de frontend usa o mesmo build e tem controlos específicos para o vocabulário, a Jinja datada e o parser de canais. [Frontend](frontend.md)

Com os 7 012 quartetos oficiais dos T2 naturais P97/P106, o cenário seletivo cobre 4,631 a 8,917 GB de páginas diferentes em cada tile de 32. O cenário integral, se for o primeiro ticket em todas as 35 camadas elegíveis, alcança 59,222 GB em cada uma. Na tile de 20, o conjunto seletivo sobe para 15,635 GB. A ordem de cálculo por camada permite reutilizar memória ao longo da tile. A conversão de páginas em bytes de disco requer observar a execução e a cache do SO. [Comparação de cada tile e dos 46 passos de decode](natural_pages/README.md)
