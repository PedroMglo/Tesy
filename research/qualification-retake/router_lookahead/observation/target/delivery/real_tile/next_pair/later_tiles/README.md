# Três ofertas sem consumidor na quinta tile

Na call 1 da C292, a passagem CPU0→CPU1 das posições **128–159** é a primeira com quatro ofertas, pelo menos uma previsão falsa e referências independentes de ambas as camadas. O seletor escolheu os experts **6, 13, 20 e 21**, nessa ordem. As rotas oficiais da CPU1 consumiram apenas o 20. O resultado qualifica uma intervenção física nesta tile com estado quente. O ganho temporal permanece por medir. [Protocolo da seleção](protocol.md) · [Evidência compacta](evidence.json)

As tiles 2–4 forneceram 72 pares anteriores, com E33, ranks oficiais e procura observada em todos. Faltavam os dois FFN de referência da C270 para essas posições. Em 45 pares havia quatro ofertas e pelo menos uma sem consumidor, dois tinham menos de quatro ofertas e 25 consumiram todas. O controlo da primeira tile repetiu os quatro acertos em cada um dos 24 pares. A ordem do journal determinou a seleção. A C292 usa um prefill de 189 posições com callback de captura; o efeito sobre uma conversa natural permanece desconhecido. [Seleção fria](../README.md) · [Seletor](select_pair.py)

**Grafo e estado.** A parte 23 forneceu 21 ficheiros independentes por camada, incluindo post-norm, logits do router, top-4, pesos de mistura, oito pares de IDs/máscaras e os 92 160 F32 finais. Foram autenticados os 128 ranks ativos em cada camada contra a parte 116, com identidade de slot e geração observada para cada demanda. A amostra histórica de comparações diretas dos bytes dos experts inclui zero linhas para este par e posição. Cada residente tem, no entanto, um registo PFJ de reserva, READ do pack pelo FD correto, três SET da mesma geração e publicação no mesmo worker. O hash C290 das três matrizes encontra-se no plano para a verificação dos bytes pelo próximo processo. [Reconstrução](state.py)

| No início da previsão E35 | CPU0 | CPU1 |
|---|---:|---:|
| Slots READY | 40 | 40 |
| Remaps / reservas anteriores validados | 32 / 137 | 32 / 92 |
| Experts vistos / relógio de utilização | 79 / 649 | 77 / 604 |
| Entradas de hotness diferentes de zero | 0 | 0 |
| Reservas oficiais nesta tile | 28 | 4 |
| Remaps / reservas validados até ao último E23 | 40 / 165 | 40 / 96 |
| Relógio de utilização no último E23 | 805 | 736 |

Do arranque vazio até ao E35, o replay das decisões do C291 leva a 140 chamadas do manager. A FIFO, a lista de claims e o conjunto LOADING estão vazios na entrada da tile (ordinal 50 663), no E35 (50 696), ao sair a última oferta (50 734) e no último E23 de CPU1 (51 369). Os quatro workers tinham efetuado entregas antes da entrada. A reconstituição conserva binding, geração, idade de cada slot, hotness, seen, relógio e histórico da wave/parking e foi confrontada com as reservas seguintes, incluindo a vítima em cada expulsão. As palavras de política são derivadas do código selado; as publicações e os slots são observados em gravação. A prontidão dos buffers privados dos novos workers e a duração de acordar/escalonar threads precisam de validação na fixture. [Política de vítimas](../../../../../../../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/replay/manager.py)

| Operação por processo | Janelas de 13 221 888 B | Bytes pedidos ao pack |
|---|---:|---:|
| Reposição pré-relógio, 3 SET por binding | 80 | 1 057 751 040 |
| Reservas oficiais, mesmo target | 32 | 423 100 416 |
| Três falsas se todas forem lidas | 3 | 39 665 664 |
| Limite conservador com as quatro ofertas | 116 | 1 533 739 008 |

Os 240 SET da reposição entregam 1 057 536 000 B ao primário. O teto de 116 pedidos admite as 32 reservas e até quatro leituras de oferta, com um possível acerto em comum. A reconstituição em disco pode aquecer o dispositivo. O próximo gate exige conferir o estado inicial e terminal, os pesos por binding e os golds no processo real antes de medir OFF/ON–ON/OFF. [Protocolo da fixture quente](../../warm_pair/protocol.md)

**Preparação e reprodução.** O seletor R01 preservou uma falha de validação das posições do GPU35 podado. A correção restringiu exclusivamente a verificação E33 à população CPU do contrato. O primeiro ensaio de reconstrução ocorreu antes de um ajuste de formatação e permanece separado. Os dois replays finais do commit `8e048511` são byte a byte idênticos em todos os ficheiros, incluindo o recibo `45cdefb3…3860`. Leram 21 984 785 B de fontes, parâmetros e capturas e zero bytes do pack. O plano sela 99 chaves distintas no índice integral, incluindo as 80 residentes e as três ofertas falsas. O preparador `4d032328` gerou todos os 71 tensores/ficheiros da interface fria mais `warm-state.json`, com 5 008 569 B de metadados e dados anteriores e 270 leituras verificadas de bias (3 110 400 B). A nova preparação tem SHA `64c6b083…aa03`. [Contrato e volumes da preparação](prepare.md)

```sh
python3 -IB "$UNIT/test_state.py"
python3 -IB "$UNIT/test_prepare.py"
python3 -IB "$UNIT/state.py" --part23 "$PART23" --part116 "$PART116" \
  --backend "$C291" --c7 "$C7" --bundle "$ROUTER_PARAMS" \
  --manifest-dir "$DERIVED_C291" --new-output-dir "$NEW_STATE"
python3 -IB "$UNIT/prepare_warm.py" --state-dir "$NEW_STATE" \
  --cold-dir "$SEALED_COLD_INPUT" --manifest-dir "$DERIVED_C291" \
  --new-output-dir "$NEW_INPUT"
```

Os destinos privados contêm os inputs numéricos e as origens de cada reserva. Os manifestos e os quatro testes sintéticos permitem verificar as duas etapas.
