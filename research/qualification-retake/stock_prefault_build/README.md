# Stock com prefault opcional no carregador

**MEDIDO — PASS_PRIVATE_GOLD_AND_CANDIDATE_BUILD.** A recompilação de controlo reproduziu byte a byte a `libllama` stock. O candidato expõe a escolha do prefault na mesma chamada do carregador. O servidor resolveu a biblioteca privada e devolveu a versão esperada nos dois casos. O resultado admite a verificação numérica e de mapeamento com um GGUF pequeno em CPU. [Recibo da construção](build-r1/receipt.json) · [Fixture CPU](tiny.md)

## Proveniência e custo

A medição partiu do commit Tesy `ecb6db76cd28495d6473cabc64be1b32244a85c8`, árvore limpa `5e4b9d3dc97a23bdae22b97e5966d0becb6f3cfa`, e do build B de llama.cpp no pin `e95426f16982054c379ca7bdc8186996dd22f0fe`. Em cada fase, GNU 15.3.1 recompilou unicamente `src/llama-model.cpp` e ligou o objeto aos outros 43 objetos originais, às quatro bibliotecas GGML e ao stub CUDA do build. O programa conferiu os 49 inputs e a biblioteca stock novamente após a ligação. O recibo identifica as ferramentas, os comandos e os ficheiros por SHA-256. [Protocolo congelado](protocol.md) · [Build stock B](../stock_build/attempt-b/receipt.json)

| Imagem | SHA-256 de libllama.so.0.9.0 | Fase |
| --- | --- | ---: |
| Stock e controlo recompilado | `717a7e3dc18ae58585c6df1af2454c5b441c171258b7100ae7e11530e02265b8` | 6,302 s |
| Candidato | `34ce470fac8b70d58602ba979f014616b9a8b7a9593b55a5e8436116f6ceb767` | 6,145 s |

As três imagens coincidiram nos 6 089 símbolos exportados verificados, dependências dinâmicas, SONAME e RUNPATH. Ambos os testes `llama-server --version` devolveram build 1001, commit e95426f. O processo total demorou 12,71 s, com pico de 488 264 KiB de RSS e 12 611 435 bytes de ficheiros novos contabilizados pelo programa. Limites pré-registados de 120 s e 2 GiB de espaço virtual por fase, e 150 MiB de ficheiros novos por tentativa. SHA-256 do recibo publicado `5f58a70ddc141a7a874776429c61e37169a9d7694e8b54e44e23aec0f9c69e02`.

## Reprodução

Na árvore limpa da medição, indicar em `STOCK_E95426_BUILD_ROOT` o diretório autenticado que contém `source/` e `build/`, incluindo a base de compilação CMake, o grafo Ninja e os objetos originais. Escolher para `NEW_PRIVATE_OUT` um caminho novo fora desse diretório. Objetos, bibliotecas, comandos e logs de ligação são escritos na saída privada.

```sh
python3 -B research/qualification-retake/stock_prefault_build/test_build.py
python3 -B research/qualification-retake/stock_prefault_build/build.py \
  --stock-build-root "$STOCK_E95426_BUILD_ROOT" --new-output-dir "$NEW_PRIVATE_OUT"
```

No código do candidato, `TESY_STOCK_LAZY_MMAP` ausente ou `0` seleciona o prefault stock, `1` passa `false` a `ml.init_mappings` e qualquer outro valor gera erro ao atingir essa chamada. O argumento de mlock é preservado. Nesta etapa, `--version` verificou a ligação. O efeito nos mapeamentos, a igualdade dos logits, a pressão de memória no arranque E20 e o desempenho de uma conversa requerem observações próprias. [Semântica do prefault e ensaio memfd](../stock_prefault/README.md) · [Resultado de arranque E20](../aster_ram_budget/README.md)
