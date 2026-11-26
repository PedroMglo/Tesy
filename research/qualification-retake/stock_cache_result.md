# O stock pode usar páginas reclamáveis do GGUF no USB

**GO apenas para preparar um binário stock independente e testar o arranque.** No pin `e95426f16982054c379ca7bdc8186996dd22f0fe`, o mapeamento CPU permite manter a fonte dos experts em páginas limpas, reclamáveis pelo Linux. O arranque tenta povoar todo o ficheiro de 63 387 346 208 B. Sob pressão podem ocorrer leitura antecipada, descarte e novas leituras pelo USB antes de o servidor ficar pronto. A capacidade, o tempo de arranque, a paridade do backend e a conversa neste regime continuam **NOT_RUN**. M3 PARTIAL e M4 NOT_MET.

## Percurso de uma falta

Com o comando congelado, `-cmoe` coloca as matrizes e biases de experts no host. `--no-repack --no-host` deixa disponível o buffer CPU normal. Esse backend implementa `buffer_from_host_ptr`. Quando o tipo de buffer é o predefinido e a implementação aceita o ponteiro, o loader associa as vistas aos bytes do GGUF; se a condição falhar, abre-se a via de alocação e cópia explícitas. As opções de carregamento, GPU, cache e KV constam do [protocolo](stock_cache.md). [CPU](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/ggml/src/ggml-cpu/ggml-cpu.cpp#L393-L426) · [Seleção de buffer](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-model.cpp#L1990-L2068) · [Associação ou cópia](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-model-loader.cpp#L1713-L1756)

Neste Linux com um nó NUMA online, o modelo pede prefetch. Sem intervalos lazy, o construtor usa `PROT_READ`, `MAP_SHARED|MAP_POPULATE` e `POSIX_MADV_WILLNEED`. O kernel tenta antecipar as páginas e pode reclamá-las ao longo da leitura. O modo escolhido dispensa `mlock`; o caminho lazy do pin exige a marca `TENSOR_READ_LAZY`, ausente nas matrizes desta arquitetura. Esta tentativa integral impede assumir um arranque a frio que custe só os primeiros experts escolhidos. [Mapeamento](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-mmap.cpp#L482-L524) · [GPT-OSS](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/models/openai-moe.cpp) · [mmap(2)](https://man7.org/linux/man-pages/man2/mmap.2.html)

O target fornece os quatro IDs. Um hit executa o expert no device. Na configuração `--moe-cache-cpu-share 0`, uma falta copia os pesos selecionados do host para os bancos CUDA. A fonte pode estar na page cache ou implicar leitura do dispositivo e readahead. Uma fração CPU positiva atribui parte das faltas à CPU depois de encher a cache, se o grafo suportar a partição. Nesse caso a CPU também precisa das páginas. Para ubatches até 32 o grafo verifica se cabe o pior conjunto de IDs da camada. Acima deste tamanho segue a via de upload de experts do scheduler. A contagem R0 de bytes com O_DIRECT e os seus tetos por braço são específicos do R0. [Cache e partição stock](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/docs/moe-cache.md) · [Implementação](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-moe-cache.cpp)

## Capacidade do candidato congelado

Contas FORMAL sobre o [recibo do header](moestream-receipt.json). Contexto 8192, uma sequência, ub32, top-4, 36 camadas iguais quanto à geometria dos experts, todos os blocos e output atribuídos à GPU, input na CPU. O envelope GPU presume colocação e operações suportadas pelo build CUDA. Os tamanhos de payload provêm dos tensores codificados.

| Local | Componente | Bytes |
|---|---|---:|
| Host, vistas de ficheiro | 36 × 128 experts, três matrizes MXFP4 de 4 406 400 B cada | 60 914 073 600 |
| Host, vistas de ficheiro | Biases de experts e tabela de embeddings Q8_0 | 159 252 480 + 615 329 280 |
| Host, alocação | Mapas I32 de 36 × 128, além do estado ClassLRU, do tokenizer, de metadados, page tables e temporários | 18 432 nos mapas |
| GPU | Três bancos de 161 slots partilhados entre as camadas, mais um slot de guarda. Payload 2 141 510 400 B, com guarda de linha CUDA e alinhamento de 128 B | 2 141 510 784 |
| GPU | Restante payload de pesos, incluindo o output | 1 685 668 608 |
| GPU | KV f16, 8 cabeças KV × 64 por K e V. 18 camadas têm 8192 células. As outras 18, com janela de 128 e tile de 32, arredondam a 256 no cache SWA compacto | 311 427 072 |

Subtotal GPU de **4 138 606 464 B**. O cap de 8 GiB menos 512 MiB deixa **3 914 457 216 B** para o contexto CUDA, padding dos demais pesos, grafo, workspace e buffers transitórios. O código e o recibo não medem esse consumo nem o total físico da RAM. As vistas CPU somam 61 688 655 360 B lógicos. O pico residente e a frequência com que o kernel precisa de refazer I/O dependem da pressão contemporânea. [Cache KV](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-kv-cache-iswa.cpp) · [Alocação CUDA](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/ggml/src/ggml-cuda/ggml-cuda.cu)

## Fixture e condição de admissão

REPRODUZIDO, sem pesos ou GPU. O [verificador](stock_cache_probe.py) compila a `moe_cache_lru` original e aplica IDs de teste a duas camadas. Quatro experts frios produziram quatro fills e, na repetição, quatro hits. A tile de 32 tokens com 128 IDs distintos produziu 128 fills e, na repetição, 128 hits. O resultado cobre o planeador. A execução do grafo e o upload continuam por medir. Duas execuções produziram o mesmo [recibo](stock_cache_evidence/receipt.json), SHA-256 `b91a01cf36bf77af772f765fb469639686a8edf7634716f2885908bc890f19bb`; a repetição consumiu 0,60 s e 120 320 KiB de RSS máximo.

```sh
python3 research/qualification-retake/stock_cache_probe.py \
  --llama-git "$LLAMA_STOCK_GIT" --new-output-dir "$NEW_OUTPUT"
```

O único build stock completo identificado na árvore de builds stock local corresponde a `4b1a27f`; o objeto Git do pin estudado está disponível. A próxima decisão exige compilar stock separado em `e95426f`, registar binário/bibliotecas e verificar a ABI congelada. Com a GPU livre e os gates vigentes, o primeiro ensaio físico seria uma única carga do ficheiro USB com warmup desativado, sem pedidos, com prontidão e encerramento. Medir sob o cgroup de recursos do projeto o tempo e os bytes até à prontidão, RAM `anon/file/file_mapped`, páginas bloqueadas, faults, eventos de pressão/OOM, leituras no dispositivo e pico CUDA. Confirmar o buffer CPU mapeado, grupo de 36 camadas, 161 slots e KV declarado. Violação do cap, fallback de colocação, OOM ou timeout preservam o FAIL. Só um arranque admitido abre a comparação de exatidão independente antes de timing de produto. [Contadores do cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html) · [Antecedentes e versão](../post-c320/literatura.md)
