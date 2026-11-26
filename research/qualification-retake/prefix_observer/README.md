# Observação das rotas do prefill C294

**GO para a fixture sem modelo. Rotas reais e neutralidade OFF/ON integradas em NOT_RUN_PHYSICAL_ADMISSION_REQUIRED.** O coletor preservou os 1 299 grupos top-4 da referência sintética, incluindo a ordem dos quatro experts em cada linha e uma ubatch multi-wave com mais de 40 experts distintos. Identificou o último FFN formalmente podado e rejeitou a falta de uma entrega obrigatória. O diário sintético teve 5 925 B. As unidades de tradução reais do contexto, do serviço e do cliente C294 compilaram na cópia do pin. M3 e M4 continuam dependentes de qualificação física. [Protocolo prospetivo](protocol.md) · [Recibo da validação](reproduced/receipt.json)

O patch C284 já identifica os pontos que veem as rotas originais com uma wave ou várias. Nessa experiência, a contagem alimenta a política de expulsão e os estados C286 pertencem a execuções com o seu próprio prefixo e perfil E. O tracer genérico `cb_eval` conserva as linhas do tensor top-k e infere a divisão entre grafos a partir das camadas observadas. Esta fixture reutiliza os pontos de C284 e a associação à máscara de saídas reais. Isola o registo da atualização de `route_hotness` e exige cobertura explícita do último FFN. [Implementação C284](../../../patches/c284-logical-route-v1.patch) · [Decisão C286](../../../results/c286-logical-route-policy-cost-20261006/decision.json) · [Tracer genérico](../../../native/tesy_moe_trace.cpp)

O harness experimental cria o objeto se receber `TESY_PREFIX_ROUTE_AUDIT=1`. Com o ambiente predefinido, o ponteiro está vazio. O caminho ON reserva até 1 MiB e sincroniza o grafo anterior antes de reutilizar a informação de ubatch. O próprio serviço entrega o array original de IDs, sob o mutex, antes da conversão para slots. Na via de várias waves, só a wave zero regista os IDs, antes de preparar o plano. As cópias, as verificações e a sincronização poderão ter custo. A posição da observação ordena as rotas conhecidas. O diário não fornece os instantes de disponibilidade dos pesos. [Patch do backend](backend.patch) · [Patch do harness](harness.patch) · [Formato e validação na escrita](prefix_routes.h)

## Leitura de um diário privado

O prefixo `TPR1` identifica a versão. O formato usa inteiros sem sinal, pouco-endianos. Os índices de chamada e ubatch começam em um. O índice de camada e a posição começam em zero.

| Registo | Campos depois da etiqueta | Interpretação |
|---|---|---|
| C | ID da chamada e total de entradas, 16 bits cada | A chamada corresponde a uma invocação de `runtime.call` no harness C294. |
| U | ID da ubatch em 16 bits, número de posições em 8 bits, pares posição de 16 bits / máscara de 8 bits | A sessão tem uma sequência contínua. A máscara é a efetivamente fornecida por `process_ubatch`. |
| R | camada, percurso S/M e número de linhas em 8 bits, seguidos de quatro IDs de 8 bits por linha | S identifica uma wave, M a wave zero de um plano multi-wave. As camadas 0–34 usam as posições da ubatch em ordem. A camada 35 usa as posições cuja máscara vale 1. |
| Z | sem campos | O último FFN tinha zero linhas pela máscara. Ausência de uma camada com linhas esperadas invalida o diário. |
| E, D | sem campos | Fecho da ubatch e da chamada depois da conferência da cobertura. |
| P, I | sem campos | Corte após o prefixo e após o incremento, respetivamente. |
| F | sem campos | Fecho após a fase de decode. Só então o harness pode publicar o ficheiro privado. |

`journal.records` devolve grupos ordenados, marcadores de poda e os dois cortes. Para uma política causal, consumir apenas grupos anteriores ao corte considerado. Aceitar resultados só depois de validar o fecho integral. `journal.summarize` faz essa validação e devolve contagens e digests da matriz 36 × 128 em cada corte. O leitor independente rejeitou truncagem, bytes posteriores ao fecho e a substituição do marcador de poda. [Leitor](journal.py) · [Fixture C++](fixture.cpp)

## Validação e reprodução

```sh
python3 -B research/qualification-retake/prefix_observer/verify.py \
  --backend "$TESY_C294_BACKEND" --new-output-dir "$TESY_NEW_OBSERVER_OUT"
```

Omitindo `--backend`, o mesmo comando corre a fixture e a referência independente. Com o pin fornecido, o verificador aplica os patches em temporários e compila os três objetos com GCC 16.2.1. A saída do assembler para o cliente é descartada. A primeira repetição independente revelou que os dois objetos do backend podiam ter tamanhos iguais e digests diferentes em diretórios temporários distintos. Após fixar os caminhos incorporados pelo compilador para o overlay, o backend e o projeto, duas compilações em raízes novas produziram os mesmos SHA-256. Também coincidiram o executável da fixture, o diário, os cortes e as linhas de compilação normalizadas. [Aditamento prospetivo](reproducibility.md) · [Verificador](verify.py)

| Objeto compilado | Bytes | SHA-256 idêntico nas duas raízes |
|---|---:|---|
| `llama-context.cpp` | 263 072 | `c3f06a331f0f1074876d2c9ac77c471caebd0470ba280500bd714a0a06fac41f` |
| `llama-moe-stream.cpp` | 395 048 | `89b7ee9838c5f33e8617a73aa22127c82c5b8d67ae079130b39571d7b102d3bc` |

A repetição dupla usou 1 827 270 B de ficheiros regulares nos temporários ao fecho e um máximo amostrado de 492 468 KiB de RSS na árvore do compilador. A fase mais demorada levou 4,271 s. Os recibos preliminares ficaram locais. Os objetos de ensaio foram eliminados com os temporários. O SHA-256 do recibo final é `063c85865e6b4a9b6da4596aa91ea940b3791a4ac0db2a13230ec94e165e6656`. [Recibo de reprodução](reproduced/receipt.json)

Para exigir a comparação com a primeira execução, usar o respetivo recibo e uma segunda saída exclusiva.

```sh
python3 -B research/qualification-retake/prefix_observer/verify.py \
  --backend "$TESY_C294_BACKEND" --new-output-dir "$TESY_NEW_REPRODUCTION" \
  --compare-receipt "$TESY_NEW_OBSERVER_OUT/receipt.json"
```

O ensaio cobre uma sequência, contexto até 8 192, ubatch até 32, 36 camadas e quatro experts distintos entre 128. Com a admissão física satisfeita, a próxima verificação requer um build e cliente coerentes com o patch, origem/hashes completos, pares OFF/ON com os mesmos IDs de entrada e posições, logits completos finitos e IDs de saída, envelope, recursos e custo integrado da observação por fase. Os 1 299 grupos e os digests acima pertencem exclusivamente à fixture. O GGUF original está verificado no portátil. Esta unidade consumiu zero forwards, GPU e downloads. [Inventário do portátil](../host.md)
