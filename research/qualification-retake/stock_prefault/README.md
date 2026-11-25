# Prefault do GGUF no arranque stock E20

**PASS da fixture de mapeamento.** No stock e95426f, a inferência pode manter o mesmo ficheiro aberto em mmap e adiar o primeiro acesso às suas páginas se receber `false` na criação dos mapeamentos. O servidor oficial deste pin não expõe essa escolha isoladamente. O resultado dá fundamento a uma ablação do loader. Ficam por medir o PSI e o custo total até à resposta do 120B sob essa ablação.

## Onde parou E20

| Stock Aster, SWA completa, 161 slots de cache CUDA nas 36 camadas | Máximo de PSI full avg10 nos primeiros 25 s do supervisor | Primeira linha CPU_Mapped no log do servidor | READY no supervisor |
|---|---:|---:|---:|
| E10, orçamento | 4,03% | 20,688 s | 29,623 s |
| E10, divisão das fases | 4,57% | 21,768 s | 31,488 s |
| E20, divisão das fases | 14,23% | ausente | HOST_PSI_PERSISTED |

Em E20, o servidor anunciou o carregamento por mmap aos 0,435 s do seu relógio e fechou aos 24,67 s de execução com zero pedidos. A última observação de PSI publicada ocorreu aos 23,594 s do supervisor. Este já registava pelo menos 10% desde os 13,748 s. O supervisor verifica a persistência por dez segundos antes de anexar a amostra ao journal, pelo que a observação que provocou a saída consta apenas do motivo terminal. Os dois relógios têm origens distintas.

O cgroup terminou com 54 429 261 824 B de leitura atribuída ao NVMe, um pico de memória de 20 939 010 048 B e 4091 ocorrências de memory.high. O máximo amostrado de memória de ficheiros foi 20 580 601 856 B. Não houve OOM ou swap. Esta combinação localiza pressão durante a inicialização dos tensores. O log omite os limites da chamada `init_mappings`. O PSI global incorpora as restantes atividades do host. As três execuções conservaram o estado natural da page cache. [E10 orçamento](../aster_budget/README.md) · [E10 fases](../aster_split/README.md) · [E20](../aster_ram_budget/physical-r1/receipt.json)

## Teste da explicação

Em `src/llama-model.cpp:1990`, o carregador de inferência chama `ml.init_mappings(true,…)` antes da criação das vistas e de `load_all_data`. O segundo argumento governa o mlock. O carregador converte `true` em `size_t(-1)` e `false` em zero ao criar a vista mmap. Em Linux, sem NUMA ou ranges lazy, o primeiro caso pede MAP_POPULATE e aconselha WILLNEED em todo o ficheiro. Ambos usam MAP_SHARED, PROT_READ e POSIX_FADV_SEQUENTIAL. O quantizador já usa `init_mappings(false,…)`. [Carregamento normal](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-model.cpp#L1990) · [Escolha do tamanho](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-model-loader.cpp#L1423) · [Implementação Linux](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-mmap.cpp#L480) · [Quantizador](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-quant.cpp#L1042)

Os modos públicos de carregamento que abandonam mmap mudam a colocação. O modo lazy depende das marcações TENSOR_READ_LAZY, ausentes nos experts GPT-OSS deste pin. O portátil expõe um só nó NUMA. O teste `ggml_is_numa()` exige vários nós e, quando ativo noutro anfitrião, o modo NUMA também altera a afinidade e o conselho de acesso aleatório. Estas opções não fornecem o controlo isolado pretendido. A unidade stock_paging já investigou o reclaim sob o cgroup E10 mantendo o prefault ativo. [CLI stock](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/common/arg.cpp) · [Stock paging](../stock_paging/README.md)

A fixture liga dois objetos reais do build aos símbolos nativos de mmap e de aconselhamento através de wrappers que registam os argumentos e executam as operações. Um memfd de 4 MiB previamente preenchido manteve 1024 páginas em cache nos dois braços. A contagem de páginas residentes pertence ao inode.

| Prefetch | MAP_POPULATE | WILLNEED | RSS da nova vista antes de ler | RSS após comparar cada byte | Bytes iguais à referência |
|---|---|---|---:|---:|---:|
| true | sim | sim | 4096 KiB | 4096 KiB | 4 194 304 |
| false | não | não | 0 KiB | 4096 KiB | 4 194 304 |

A presença das páginas no ficheiro e a sua instalação na tabela de páginas do processo são observações separadas. Um memfd quente permite distinguir a segunda sem inferir latência ou tráfego de um NVMe. A fixture levou 0,457 s, usou até 100 808 KiB nos filhos, incluindo compilação, e escreveu 71 138 B privados. [Protocolo congelado](protocol.md) · [Recibo R1](evidence-r1/receipt.json)

## Reprodução e próximo contraste

Definir `STOCK_BUILD` para a raiz que contém `source/` e `build/` do stock pinado e `NEW_PRIVATE` e `NEW_OUTPUT` para dois destinos inexistentes. A fixture verifica os hashes de fontes, objetos e biblioteca. Requer Linux com páginas de 4 KiB e o compilador congelado.

```sh
python3 research/qualification-retake/stock_prefault/verify.py \
  --stock-build-root "$STOCK_BUILD" --new-private "$NEW_PRIVATE" --new-output-dir "$NEW_OUTPUT"
```

A fronteira mínima para a inferência é um opt-in no argumento de `init_mappings`, com o valor stock por omissão. A colocação de pesos, os 161 slots de cache CUDA nas 36 camadas, o KV F16, a SWA completa, o template e o grafo podem ficar iguais. A leitura por demanda, o readahead do kernel e as cópias dos tensores obrigatórios continuam a custar. Um ganho no arranque pode reaparecer como demora no primeiro pedido. Para testar atribuição, comparar stock independente, build modificado com a opção inativa e o mesmo build com a opção ativa. Registar entrada e saída de `init_mappings` e de `load_all_data` no relógio do servidor, bytes de cgroup/NVMe, pressão global e tempo de cliente até resultado. Conservar C55/C118, cap/high/PSI e a identidade do GGUF e dos ELFs. Validar os outputs do target e os pedidos antes de uma conclusão de produto. Esta unidade apenas executou a fixture sem modelo.
