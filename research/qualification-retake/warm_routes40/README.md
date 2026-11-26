# O grafo roteado do próprio R0 pode servir de referência?

**O cliente reparado passou o canário físico de 16+1+1. A comparação de frequência a 40 slots exige os quatro braços completos.** O cliente de 40 slots original regista dois tamanhos finais por chamada no modo OFF. Mesmo conservando os 33 logits de C280, não é possível recuperar desses tamanhos a sequência de grafos do prefixo ou o top-4 por posição. A janela de serviço C294 só começa após o prefixo. A pergunta sobre a frequência acumulada P+I motivou uma testemunha independente comum aos braços OFF e ON. [Pergunta, comparadores, recursos e critérios](protocol.md)

O novo cliente lê os tensores lógicos `ffn_moe_topk-L` no callback GGML já instalado. Compara camada, tipo I32, dimensões, strides, posição e cada um dos quatro ranks. Na RoPE da camada zero, `Qcur-0` fornece o vetor de posições efetivamente consumido em `src[1]`. A camada final usa o índice lido nos dois GET_ROWS que alimentam `ffn_inp-35`. Um grafo sem saída pode omitir o último router ou conservá-lo com zero linhas. O N3 deste ensaio identifica grafos roteados por estes pontos e pela sequência obrigatória de camadas; o desenho não exige comparar cada operador não roteado. A recolha dos tensores sincroniza partições do GGML em ambos os braços. Os tempos desta configuração só medem os observadores no cliente de diagnóstico. [Hook no cliente](client.patch) · [Leitor independente](witness.py)

### Teste positivo e contraexemplos

A fixture passou pelo escalonador e pelo backend CPU GGML reais, com uma thread e dados sintéticos declarados. Duas ubatches de 3 e 2 posições exercitaram RoPE, a seleção final, os ranks em views de 512 B de stride e dois modos de poda. As duas variações produziram o mesmo journal de 176 linhas. Trocar os ranks ou trocar só as etiquetas de duas posições conserva a geometria e o histograma das contagens, mas falha quando o leitor compara as linhas com as etiquetas calculadas independentemente. Remover a camada 17, alterar uma posição efetivamente usada ou o índice final também falha. Nenhum peso de modelo foi aberto pela fixture. [Fixture de grafo](graph_fixture.cpp) · [Build inicial](build-attempt-01/receipt.json)

O canário físico R1 foi preservado em FAIL. OFF terminou com `invalid target topk name` antes de publicar os três vetores e ON ficou NOT_RUN. O parser antigo interpretava um tensor derivado como se o nome tivesse de ser canónico. O R2 acrescentou ao grafo de teste o `ggml_cont` que o planeador usa efetivamente no R0. A biblioteca gerou `ffn_moe_topk-0 (cont)` e o header R1 selado reproduziu a exceção. O stderr físico R1 não identifica o sufixo concreto. O reparo só seleciona o nome canónico inteiro. A fixture confirmou que substituir o nó canónico por um alias ainda faz falhar a cobertura e que o journal válido continua bitwise igual. [Aditamento de reparação](canary/alias-repair.md) · [Gate do canário](canary/alias-r2/protocol.md)

O segundo cliente longo regista também os campos expert, geração, estado e claim em 1 440 destinos no corte I, além da dimensão da fila. A operação tenta o mutex uma vez, sem drenagem adicional. Só converte e grava o vetor após a última chamada. A fixture não modelada usou o gestor C294 real, 23 064 B reservados no objeto, e confirmou que modificar uma geração depois da cópia não altera o registo já obtido. Rejeitou fila pendente, slot reclamada e mutex ocupado. Os dois C294 históricos de cada caso concordam no vetor de I; o gate exige igualdade integral com a nova observação antes do replay de vítimas. [Contrato de I](boundary-protocol.md) · [Verificador](boundary.py)

| Artefacto model-free | SHA-256 | Tempo de build e testes | RSS máximo de um filho |
|---|---|---:|---:|
| Cliente longo R2, 40 slots | a831c1831acf7e5dd17cc2e04b57863ab07d2c05db44d3b554331464819277eb | 8,280 s | 591 704 KiB |
| Cliente curto R2, 32 slots | e6a48391d28b777f898e2879572310ef1b615b4b8d899ab8d93eb1a6e8619830 | 1,563 s | 250 572 KiB |

Ambos ligam a libllama C294 reparada previamente a nível de observador e as quatro bibliotecas GGML C269 já qualificadas; o build R2 altera os clientes. O binário longo e a fixture guardada ocupam, com fontes e logs privados desse build, 608 291 B. O executável canário mantém toda a CLI do diagnóstico curto. A comparação por braço no supervisor termina antes do ON se o gate independente do OFF falhar. Os limites de hardware e comparadores aplicam-se a cada execução física correspondente. [Recibo longo R2](build-attempt-02/receipt.json) · [Recibo curto R2](canary/build-attempt-02/receipt.json) · [Mutação do supervisor](canary/test_supervisor.py)

## Resultado do canário no portátil

**PASS em 16+1+1 com 32 slots.** Os dois processos do cliente R2 reproduziram os 603 264 logits finitos da referência e o mesmo witness de 3 146 B. As 2 532 escolhas observadas coincidiram, em posição, camada e rank, com os 633 grupos top-4 do serviço. No braço ON, o TPR1 contemporâneo também conferiu byte a byte com a referência do canário anterior. Foi possível verificar a associação dos quatro ranks independentemente nos dois modos do observador. [Recibo físico R2](canary/physical-r2.json)

| Braço | Processo | Parede com admissão | Memória de pico do cgroup | VRAM de pico |
|---|---:|---:|---:|---:|
| OFF | 10,204 s | 70,863 s | 12 482 461 696 B | 5 700 MiB |
| ON | 10,214 s | 70,936 s | 12 492 742 656 B | 5 700 MiB |

Houve 61 amostras antes de cada arranque, zero swap de workload e encerramento dos dois PID e cgroups. O primeiro ensaio físico R1 parou no OFF ao interpretar um nome derivado do GGML e conservou o erro. A fixture posterior reproduziu o erro com o cabeçalho R1 e um consumidor GGML real. Os três grafos do canário curto emitiram uma posição final cada. O caso de uma ubatch do modelo sem saída da última camada requer a família longa. [Falha física R1](canary/physical-r1.json) · [Reparação e contraprova](canary/alias-repair.md)

### Reprodução sem pesos

Usar o build privado R0 de prefixo, a pasta das libs GGML C269 e o build anterior do canário 32. O programa recusa reaproveitar destinos e consulta o commit preservado da primeira testemunha para o teste negativo. O driver de build medido R2 está no commit `0dc96f7b6569d2a0dc56e6c19af6b5689fd0536c`. Depois da medição, dividiu-se em duas linhas uma string de proveniência desse driver. O conteúdo de entrada, as flags e os binários compilados são os do recibo.

Após normalizar uma linha vazia de contexto em cada patch, aplicou-se tanto a versão do commit acima como a normalizada ao mesmo fonte de origem, em diretórios temporários, com GNU `patch -p1 --fuzz=0 --batch`. As duas aplicações produziram em cada caso um ficheiro idêntico byte a byte ao fonte preservado do build. A verificação dispensou recompilação.

| Patch | SHA-256 do fonte C++ resultante |
|---|---|
| `client.patch` | `495af0ed9811f6bbe2236dd77d0e23eb65c7b1e53d97b8a7eced97614394a3de` |
| `boundary.patch` | `44f7fda2602e20b087565c02d880c3d29bef46a0b6a2fe8726f65eb50962654a` |
| `canary/client.patch` | `fb2fedf56b5acf2bc6bb2cea739bbe55c74fd50c8180e2be27a08e1749e37fc5` |

```sh
python3 -B research/qualification-retake/warm_routes40/build.py \
  --parent-build "$PREFIX_BUILD" --ggml-bin "$C269_GGML_BIN" \
  --new-workspace "$NEW_PRIVATE_LONG" --new-receipt "$NEW_LONG_RECEIPT"
python3 -B research/qualification-retake/warm_routes40/canary/build.py \
  --canary-parent "$PREVIOUS_CANARY32_BUILD" --prefix-build "$PREFIX_BUILD" \
  --ggml-bin "$C269_GGML_BIN" --new-workspace "$NEW_PRIVATE_SHORT" --new-receipt "$NEW_SHORT_RECEIPT"
python3 -B research/qualification-retake/warm_routes40/canary/test_supervisor.py
```

O sinal de P+I precisa dos dados das duas fixtures R0, de paridade dos 33 logits, das 78 056/74 836 linhas em ordem, do estado I contemporâneo e da comparação com P-only e C286. Um resultado favorável nessa contagem só admite estudar a política física. [Referência independente de decode](../warm_route_reference/protocol.md)
