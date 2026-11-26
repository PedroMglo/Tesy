# Residência no primeiro decode de C294

**REPRODUZIDO / TRACE_DERIVED.** A pertença aos 36 pools no fim de `prefill153` é identificável nos quatro braços trace-ON de C294. Cada braço entra no decode com 1 411 slots residentes, 29 vazios e zero slots em carregamento ou reclamados por workers. As duas repetições de cada caso concordam nos 1 440 destinos físicos, incluindo geração e estado. A aplicação a Belady deve começar com os experts reais de cada camada. Um algoritmo causal teria de justificar como escolhe vítimas sem as referências futuras. [Recibo agregado e hashes de 12 entradas](cache_boundary_evidence/receipt.json) · [Manifesto congelado](../../results/c294-feature-ready-service-window-20261006/raw-manifest.json)

| Braço | Reservas novas no prefill | Vítimas residentes | Promoções da mesma geração | Publicações no prefill | Decode hits / misses |
|---|---:|---:|---:|---:|---:|
| nominal 2 ON | 1 043 | 1 042 | 372 | 1 043 | 3 527 / 1 081 |
| nominal 3 ON | 1 043 | 1 042 | 370 | 1 043 | 3 527 / 1 081 |
| código 2 ON | 2 106 | 2 103 | 1 385 | 2 106 | 3 300 / 1 308 |
| código 3 ON | 2 106 | 2 103 | 1 384 | 2 106 | 3 300 / 1 308 |

Em cada `*.native/initial.json`, o harness tirou um snapshot sob o mutex, após o prefixo e o drain da fila. Só depois ativou o trace, executou a chamada incremental de 153 tokens e emitiu o marcador de fim de call 0. O próximo marcador inicia call 1, o primeiro decode. A segunda âncora materializada é `result.json.final`, após os 32 tokens de decode e novo drain. O prefixo anterior ao snapshot dispensa reconstrução. [Fronteiras do harness](../../tools/expert_service_window.cpp) · [Estrutura dos snapshots](../../tools/block_native_run.cpp)

A reconstrução começa pelos vetores `slot_expert`, `slot_generation`, `slot_state` e `slot_claimed` de cada pool. Na ordem de registo de `events.tsv`, uma reserva seguida do evento 4 avança uma unidade de geração e substitui o dono anterior do slot. Um segundo evento 4 à mesma geração de um slot em carregamento promove a procura. O evento 5 reclama o trabalho válido. Antes de cada publicação 10, os eventos 6–9 devem completar leitura e cópia das três componentes de 4 406 400 B para o mesmo expert, geração e slot. As transições de reserva, reclamação e publicação relevantes usam o mutex do manager. Cada evento 3 confirma o estado anterior à procura. Há 4 608 dessas observações no decode por braço. O vetor completo no fim de call 0 é igual ao do início de call 1. O replay dos eventos restantes também reproduz os quatro campos em todos os slots do snapshot final. [Patch do observador](../../patches/c294-feature-service-window.patch)

O SHA-256 da matriz `[camada][slot][expert, geração, estado, reclamado]` em JSON compacto é `671354649bd647f6e4cf20556bfda018bf68bde6c54112304ab33313f2638fbf` nos braços nominais e `49f3dc0f809ed4d60834820747c4790f9166cb5128fe0f0e8aacdacd9adf6b41` nos de código. Este resultado identifica conteúdo e disponibilidade lógica na fronteira do decode. A reconstrução não mede trânsito físico, posse de workers fora destes eventos, pins transitórios, valores em KV ou os contadores auxiliares completos de uma política contrafactual. O custo causal das substituições alternativas continua a exigir teste próprio.

A API `boundary(raw, name)` devolve 36 conjuntos de IDs locais 0–127 em ordem de camada. O argumento `raw` é o diretório `raw/` da C294 original e `name` segue, por exemplo, `c294-nominal153-2-on`. O solver que codifica um expert globalmente usa `128 * camada + expert`. Em cada execução o verificador confere tamanho e hash das três entradas desse braço antes de devolver os conjuntos. A reanálise dos quatro braços consumiu 0,33 s e 42 384 KiB de RSS, com zero forwards. Três testes de falha em memória foram rejeitados ao saltar uma geração, retirar um fim de cópia e alterar a âncora final; os originais permaneceram íntegros. [Verificador](cache_boundary.py)

```sh
python3 -B research/qualification-retake/cache_boundary.py \
  --raw-dir "$TESY_C294_RAW" --new-output-dir "$TESY_NEW_BOUNDARY_OUT"
```
