# Que bytes exige o arranque stock até READY?

**A fonte e os recibos disponíveis não demonstram um piso de 20 GiB de leitura do GGUF ou de RAM residente para o candidato com prefault desativado.** Na colocação stock observada, os grandes tensores de experts na CPU podem continuar como vistas do ficheiro reclamáveis. A sonda de dois tokens que precede READY continua a executar trabalho real. Um ensaio do stock original com SWA completa já chegou a READY sob um cgroup de 10 GiB. No E20, o stock original terminou por pressão persistente do anfitrião antes de READY, depois de o cgroup contabilizar 54 429 261 824 B lidos. Esses bytes pertencem ao controlo com prefault ativo. A chegada do candidato a READY e o custo dos pedidos continuam por medir. [Stock E10 com SWA completa](../aster_split/README.md) · [Falha E20](../aster_ram_budget/README.md)

## O caminho do ficheiro ao primeiro pedido

1. O perfil Aster usa o GGUF original, mmap, lazy de tensores desativado, `--no-repack --no-host --fit off -ngl 99 -cmoe`, cache de experts de 2048 MiB, partilha CPU zero, contexto 8192, ub32, uma slot, dois KV f16 com SWA completa e `--no-warmup`. O protocolo conserva a Jinja e a data do cliente. O pin é `e95426f16982054c379ca7bdc8186996dd22f0fe`. O candidato muda apenas o booleano de prefault entregue a `init_mappings`. O modo de mmap continua sem mlock e o perfil conserva `check_tensors=false`. [Perfil Aster](../aster_full_ready/protocol.md) · [Defaults do modelo](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-model.cpp#L3524-L3546) · [Ablacionar o prefault](../stock_prefault_build/protocol.md)
2. Com prefault desativado, a vista é criada com `PROT_READ|MAP_SHARED` e sem pedido integral de MAP_POPULATE/WILLNEED. A chamada de `posix_fadvise` mantém o acesso sequencial. Para o buffer CPU predefinido que aceita `buffer_from_host_ptr`, o loader vincula cada tensor ao endereço correspondente. O buffer CPU normal dispensa inicialização por tensor. Com verificação de dados desativada não se percorrem os valores de todas as matrizes para validá-las. A via alternativa de cópia é usada quando o destino não aceita a vista. [Criação do mmap](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-mmap.cpp#L482-L524) · [Escolha de buffer](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-model.cpp#L1990-L2068) · [Carga dos tensores](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-model-loader.cpp#L1713-L1756) · [Vinculação do endereço](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/ggml/src/ggml-backend.cpp#L2586-L2598)
3. O perfil copia os pesos densos atribuídos à GPU. Os três bancos MXFP4 com 161 slots partilhados pelas 36 camadas, mais guarda, tomam 2 141 510 784 B de VRAM. O código zera esses bancos e inicia os mapas de slots. As cargas de experts começam quando o target fornece IDs. O registo E10 observou CPU_Mapped, 1607,61 MiB de pesos CUDA e 2042,30 MiB de cache CUDA. Os bancos KV no perfil SWA completo ocupam 288 MiB cada. O preenchimento de memória dos bancos/KV não implica a leitura de igual volume do GGUF. [Capacidade calculada a partir do cabeçalho](../stock_cache_result.md) · [Inicialização dos bancos](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-moe-cache.cpp#L569-L603) · [Serviço dos IDs escolhidos](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-moe-cache.cpp#L799-L856)
4. Antes de criar as slots do servidor, `common_context_can_seq_rm` testa a remoção parcial em KV. Na via observada limpa a memória, executa um batch com dois IDs zero, remove a segunda posição, limpa e sincroniza. Este trabalho acontece mesmo com zero pedidos de clientes e warmup opcional desativado. No E10 com SWA compacta registaram-se 262 faltas e uploads de 3 463 430 400 B nesta classe de ubatch. A SWA completa tem o seu recibo próprio de geometria e prontidão. [Chamada anterior às slots](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/tools/server/server-context.cpp#L1473-L1487) · [Operação na KV](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/common/common.cpp#L1584-L1628) · [Contador E10](../stock_log/README.md)

## Subtotal conservador de payload

Para o mesmo artefacto e a colocação observada, considerar que a sonda obtém quatro IDs diferentes em cada uma das duas posições das 36 camadas, que todos falham e que o seu serviço bem-sucedido copia o payload respetivo uma vez. Cada falta cobre três componentes de 4 406 400 B. Admitir ainda que toda a tabela de embeddings e todos os biases de experts no host sejam tocados. O cálculo sobrestima as escolhas distintas que duas posições podem fazer na presença de hits ou poda final.

| Componente | Bytes lógicos |
|---|---:|
| Pesos densos no destino GPU | 1 685 668 608 |
| Até 288 faltas da sonda × 13 219 200 B | 3 807 129 600 |
| Todos os biases de experts CPU | 159 252 480 |
| Toda a tabela de embeddings CPU | 615 329 280 |
| **Subtotal das componentes acima** | **6 267 379 968 (5,837 GiB)** |

O subtotal refere-se aos payloads identificados no percurso. Não fixa um máximo de bytes físicos no NVMe nem o pico de RSS. Metadados GGUF/tokenizer, páginas de sistema, readahead, falhas/releituras, alocações temporárias, recuperação de páginas e custos do driver têm contabilidade própria. As vistas CPU dos experts abrangem 60 914 073 600 B de endereço virtual. Uma alteração na colocação, validação integral ou via de fallback da cópia requer nova conta. Medir o candidato exigiria observar entrada e saída de `init_mappings` e `load_all_data`, `io.stat`, falhas de página, RSS de ficheiro/anónima, PSI e READY no mesmo protocolo. A demora poupada no arranque poderia reaparecer no prefill do cliente.

Inspeção reproduzível na fonte pinada e nos recibos públicos. Os comandos listam decisões de controlo e não abrem o modelo.

```sh
rg -n 'init_mappings|buffer_from_host_ptr|load_all_data' "$STOCK_SRC/src/llama-model.cpp"
rg -n 'check_tensors|ggml_backend_tensor_alloc|ggml_backend_tensor_set' "$STOCK_SRC/src/llama-model-loader.cpp"
rg -n 'MAP_POPULATE|POSIX_MADV_WILLNEED|POSIX_FADV_SEQUENTIAL' "$STOCK_SRC/src/llama-mmap.cpp"
rg -n 'ggml_backend_buffer_clear|ggml_backend_tensor_set_async' "$STOCK_SRC/src/llama-moe-cache.cpp"
rg -n 'common_context_can_seq_rm|warmup' "$STOCK_SRC/common/common.cpp" "$STOCK_SRC/tools/server/server-context.cpp"
```

## R01 da fixture sintética sob limite de memória residente

**FAIL_PRESERVED por falta de atribuição dos operadores no braço stock.** O controlador manteve `memory.max=805306368`, swap zero e 8 GiB de espaço virtual autorizado ao filho. O cliente stock abriu o minúsculo GGUF determinístico de 50 816 B, executou dois forwards em contextos independentes e escreveu 64 logits finitos (256 B, SHA-256 `aabc5c6e701c0df890d1fa21c9b590dcd4bf8a29f56390c1beb3f169848d1290`). O stdout registou a vista MAP_POPULATE e o conselho WILLNEED em toda a extensão, seguido de `CPU_MATMUL 0 16`. O observador não conseguiu atribuir os 16 resultados MUL_MAT à CPU e o processo saiu com código 9. A contagem não identifica qual backend executou esses nós. OFF, ON e inválido ficaram NOT_RUN. A igualdade de logits entre braços continua sem teste nesta identidade. [Protocolo](protocol.md) · [Recibo R01](r1/receipt.json)

O cgroup atingiu 155 254 784 B de pico sem eventos high, max ou OOM. A execução levou 0,430 s na árvore limpa `ccbe8ed9a5784de24575b891517f7e3682b0da58`. O SHA-256 do recibo original é `05791035d67b7597f10c6b2d8189b629f65f283183d56681e4873cf8196c07aa`. O modelo desta fixture é sintético. Não houve execução do 120B nesta análise.
