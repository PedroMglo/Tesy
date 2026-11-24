# Cliente C294 com observador de prefixo

**GO para o build e o arranque sem modelo.** O cliente com observador opt-in passou o self-test original do C294, o teste da CLI e a configuração OFF/ON. Nos dois arranques, o gestor abriu zero ficheiros de modelo e criou zero workers. A fixture independente reproduziu os 1 299 grupos top-4 esperados. A medição de rotas reais e da neutralidade integrada fica em **NOT_RUN_PHYSICAL_ADMISSION_REQUIRED**. [Protocolo congelado](protocol.md) · [Recibo dos 20 passos](attempt-01/receipt.json)

| Artefacto local | Bytes | SHA-256 |
|---|---:|---|
| `expert-service-window` | 292 760 | `9ae65da60a35730896a168a4a77aa4e3bb05e964db883e0649ece78663faec4f` |
| `libllama.so.0.0.9884` | 4 174 304 | `23bc41af61d232a552d79fa1048b3afa0d7250f8451983ce220465f89dadef44` |

O build partiu da árvore C294 `149078c009a40b2c69ee126cdb84091fe3e95606`, das três fontes Tesy identificadas no manifesto C294 e dos patches do observador. Compilou as 166 unidades de tradução de libllama e o cliente. A árvore de dependências gerada identificou o contexto, o grafo, o modelo, o serviço e o cliente como consumidores do layout de `llama-moe-stream.h`. A receita ligou as quatro bibliotecas GGML já compiladas do C269 congeladas em C294. Foram usadas as opções Release da receita, GCC 16.2.1, CMake 4.3.0 e Ninja 1.13.2. [Receita original](../../../tools/expert_window_build/CMakeLists.txt) · [Observador](../prefix_observer/README.md)

O loader encontrou a nova libllama junto ao executável e cada GGML no caminho previsto com o digest congelado. O inventário no próprio processo, igual em OFF/ON, contém 18 objetos mapeados com SHA-256. As bibliotecas CUDA apareceram no mapa de arranque. O probe correu com visibilidade CUDA vazia e terminou antes da inicialização de backend, sem carregar pesos ou executar kernels. As bibliotecas abertas posteriormente e o comportamento do OpenMP com trabalho real exigem observação na execução correspondente. [Probe do cliente](client-probe.patch) · [Inventário do loader em `startup_mapped_objects_sha256`](attempt-01/receipt.json)

A execução levou 43,087 s. O maior RSS amostrado numa árvore de processos foi 1 576 668 KiB e o máximo amostrado de ficheiros regulares no workspace privado foi 26 104 857 B. O erro de uso sem argumentos e a rejeição de `TESY_PREFIX_ROUTE_AUDIT=0` deram o código 1 previsto. O valor `1` ativou o observador e a ausência da variável deixou o ponteiro vazio. O digest do recibo é `b5bccd6b296d9d12ebd92cbfb9cb1404495b62f742b59d0473e29fae288f8604`. A estimativa de impacto sobre o pedido continua a exigir IDs e logits comparáveis, tempos OFF/ON e recursos no portátil.

## Reprodução no portátil

Os binários, as fontes de compilação e os logs desta execução ficam em `build/qualification-prefix-r0-20261124-a/` na checkout persistente do portátil. Os comandos seguintes conferem o cliente já construído em ambiente limpo.

```sh
TESY_PROJECT=/mnt/sdisk-ssd-ext/Tesy/repo
TESY_PROBE="$TESY_PROJECT/build/qualification-prefix-r0-20261124-a/cmake/bin/expert-service-window"
sha256sum "$TESY_PROBE" "$(dirname "$TESY_PROBE")/libllama.so.0.0.9884"
env -i PATH=/usr/bin:/bin CUDA_VISIBLE_DEVICES= "$TESY_PROBE" --prefix-config-probe
env -i PATH=/usr/bin:/bin CUDA_VISIBLE_DEVICES= "$TESY_PROBE" --self-test
```

Para reproduzir o build, escolher dois nomes ainda inexistentes em `TESY_NEW_PRIVATE_BUILD` e `TESY_NEW_BUILD_RECEIPT` e executar o verificador na raiz da checkout.

```sh
TESY_C7="$TESY_PROJECT/c7-native-placement-screen-20260927-1117utc/backends"
python3 -B research/qualification-retake/prefix_build/build.py \
  --backend "$TESY_C7/c294-service-window" \
  --ggml-bin "$TESY_C7/c269-layer-last-use/build-c269-cuda/bin" \
  --private-workspace "$TESY_NEW_PRIVATE_BUILD" \
  --new-output-dir "$TESY_NEW_BUILD_RECEIPT"
```
