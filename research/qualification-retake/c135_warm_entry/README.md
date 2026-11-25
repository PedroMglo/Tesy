# Quantos experts adicionais teriam de estar prontos antes do prefill C135?

**NO_GO condicional com 243 entradas extras. INCONCLUSIVE com 378.** No pedido nominal C135, mesmo quatro workers livres para dividir todo o serviço, com conhecimento das procuras futuras e duração dos READ reduzida para 80%, ainda precisam de pelo menos **2,455150 s** com 243 entradas. O orçamento deste pedido é **2,427104435 s**. Com 378 entradas, na escala 1 e numa execução que termina cada camada antes de iniciar a seguinte, o piso desce para **2,354871 s**. Restam **no máximo 72,23 ms** para todo o trabalho omitido que ficar exposto. O valor é uma condição necessária. O estudo não produziu uma agenda nem uma política causal que a cumpra. [Pré-registo](protocol.md) · [Recibo integral](evidence/receipt.json)

O relógio de cliente C135 trace-ON mediu 22,619140 s até ao primeiro conteúdo final. Este cenário parte do prefill de 11,706565 s e concede ao mesmo pedido todo o crédito de levar as suas 47 saídas de 11,173013 s para exatamente 6 tok/s. A lacuna de 8,885 s do C281 E20 pertence a outra conversa e medição. A referência operacional continua a ser R0 com 40 slots por camada. M3 permanece PARTIAL e M4 NOT_MET. [Orçamento C135](../prefill_entry40/README.md) · [Conversa R0 contemporânea](../nvme_conversation/evidence-20261124-r1/evidence.json)

## Pisos de serviço no mesmo pedido

| Entradas úteis adicionais antes da call 5 | Payload adicional | Mínimo de chaves frias em 5+148 | Volume / 4 a 0,8× | Por camada a 0,8× | Volume / 4 a 1× | Por camada a 1× |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0 B | 840 | 3,791256 s | 3,925297 s | 4,739070 s | 4,906621 s |
| 243 | 3 212 265 600 B | 597 | 2,455150 s | 2,568849 s | 3,068937 s | 3,211061 s |
| 378 | 4 996 857 600 B | 462 | 1,783564 s | 1,883897 s | 2,229455 s | 2,354871 s |

| Objetivo minimizado | Escala do serviço | Primeiro K cujo piso cabe | Payload adicional mínimo | Piso com K−1 | Piso com K |
|---|---:|---:|---:|---:|---:|
| Soma do worker-tempo / 4 | 0,8 | 249 | 3 291 580 800 B | 2,429418 s | 2,424276 s |
| Soma dos pisos por camada e call | 0,8 | 271 | 3 582 403 200 B | 2,428400 s | 2,423233 s |
| Soma do worker-tempo / 4 | 1 | 346 | 4 573 843 200 B | 2,428623 s | 2,422515 s |
| Soma dos pisos por camada e call | 1 | 367 | 4 851 446 400 B | 2,428605 s | 2,422447 s |

**TRACE_DERIVED e FORMAL no cenário de serviço especificado.** A call de 5 teve 45 gerações, 135 componentes e 588 884 µs de worker em READ. A de 148 teve 1 177, 3 531 e 27 623 038 µs. A segunda conserva as tiles 32+32+32+32+20. Considerando as duas calls juntas, das 1 759 chaves procuradas, 855 estão fora dos 1 424 residentes identificados. Há 16 slots desconhecidos e a melhor atribuição por camada cobre até 15 dessas 855 chaves. Ficam pelo menos 553 chaves CPU e 287 CUDA a servir uma vez antes de conceder K. Todas as 855 tinham no trace uma geração com três READ completos identificados. Para cada chave cobrou-se o menor serviço total observado numa só geração, descontando até 1 µs por componente pela resolução do relógio. A escala multiplica esse serviço. Mudanças na disposição, no acesso ou na concorrência física podem mudar os preços. [Recibo de entrada](../prefill_entry40/evidence/receipt.json) · [Recibo de serviço](../prefill_read_floor/replay-r2/receipt.json)

O primeiro piso concede sobreposição total entre camadas e calls. O segundo supõe serviço das três componentes de uma chave em série e um grupo serial por (call, camada), com todas as procuras desse grupo conhecidas à entrada e sem READ adiantado entre grupos. Cada grupo custa pelo menos o maior de dois valores, a soma dos READ dividida por quatro ou a maior cadeia individual. Dentro de um grupo, substituir uma chave isenta por outra mais cara só pode baixar as duas parcelas. A programação dinâmica distribui os créditos de identidades desconhecidas na respetiva camada e as K entradas em todas as camadas. A estimativa oferece retenção ilimitada após a primeira procura, presença no dispositivo de consumo, estado conservado entre os dois retornos e reconstrução gratuita da entrada de decode. A geometria numérica e a recomposição dessa entrada continuam por demonstrar para um executor real.

O diagnóstico de payload dá um corte muito mais baixo de **14** entradas extras a 4,5 GB/s úteis constantes, com 2,467584 / 1,753747 / 1,357171 s para K=0/243/378. Este cenário cobra só os bytes originais obrigatórios. A especificação sequencial do SSD é a origem da hipótese de taxa. Os pisos temporais da tabela usam o journal C135. [Cenário de largura de banda](../prefill_oracle40/README.md)

**Condição de reabertura.** Para K=378 com as camadas em série, todo o overhead exposto tem de caber em 72,23 ms a 1× ou 543,21 ms a 0,8×. Admitindo sobreposição entre grupos, os limites alargam para 197,65 e 643,54 ms. No cenário E20 usado para dimensionar K, 378 payloads deixam apenas 7 430 400 B para overhead antes do cap de referência. O próximo discriminante exige uma fonte anterior ao pedido para as chaves, uma política causal, os bytes realmente disponíveis antes da call 5 e a contabilização da sua preparação no prefixo que os produziu. É ainda necessário cobrar RAM e transferências por tier, computação exposta, materialização entre tiles e o primeiro decode. Um replay que identifique chaves apenas nas procuras futuras não satisfaz este gate. [Origem das capacidades](../warm_residency/README.md)

O C135 não cronometrou uma parcela demonstravelmente irredutível de atenção, router ou FFN em série com os READ neste executor. Para testar o corte de 72,23 ms falta medir, no mesmo pedido e nas duas calls, o caminho de computação entre o fim efetivo dos kernels anteriores e a primeira admissão permitida da camada seguinte, descontando todas as sobreposições. Os 3,801162 s fora de WAIT nas duas calls (0,152212 + 3,648950 s) incluem outros serviços e contenção. [Análise do despacho C135](../prefill_dispatch/README.md)

## Reprodução

Pré-registo `b3c6d804`, programa inicial `5c837e9d`. R01 terminou em 0,09 s com 42 204 KiB de RSS porque a importação do reconstrutor de slots precedeu a verificação da proveniência dos módulos do #45. O controlador registou a falha antes de calcular os pisos. A revisão `f5a881b2716129de6de55deab571f2d84246a4ab` valida primeiro as origens do #45. As três fixtures passam, incluindo 486 comparações com enumeração exaustiva de escolhas e um caso em que a atribuição ótima depende do objetivo. R02/R03 produziram os mesmos 4 527 B, SHA-256 `5250bcfef94731a8ccdba0056c8bdebc9dd1e47faca42f3160ec86ee820271e7`, em 0,58/0,57 s com 85 576/85 140 KiB de RSS. Não houve leituras de pesos, forwards ou GPU. [Falha preservada](evidence/controller-failure.json)

Numa checkout completa do Tesy, usar o trace C135 autenticado e a checkout independente do #45 em `83146dade3f90235775e4a31a8d3d8ccae3476a7`. Cada execução exige um diretório de saída novo.

```sh
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B research/qualification-retake/c135_warm_entry/screen.py \
    --repo "$PWD" --trace "$C135_TRACE" --pr45-checkout "$PR45" --new-output-dir "$NEW_OUT"
```

A comparação com o prefill de Tideway quantifica a sobreposição por dupla bufferização quando todas as 128 entradas são trazidas para cada camada. [Limite por capacidade e variante seletiva](../tideway/README.md)
