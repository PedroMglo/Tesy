# Quanto tempo de entrega chega ao consumidor?

**Com quatro workers e as mesmas quatro entregas, o ganho ao torná-las instantâneas foi de 0 ou 4 ticks, conforme o consumidor estivesse ocupado a calcular ou já precisasse dos bytes.** Quando a prontidão do dispositivo ficou por observar, as mesmas marcas de host admitiram um ganho entre 0 e 6 ticks. Quatro threads reais executaram a fixture com dados sintéticos e um relógio virtual comum. Os ticks são unidades do DAG e não têm conversão para segundos do portátil. [Pré-registo a2e8bbbd](protocol.md) · [Recibo da execução](receipt.json)

| Caso | READ + SET (worker-ticks) | União das entregas (ticks) | Espera READY do consumidor | Parede original | Parede com entrega gratuita | Ganho exposto |
|---|---:|---:|---:|---:|---:|---:|
| Cálculo oculta a entrega | 16 + 12 | 7 | 0 | 12 | 12 | 0 |
| Cálculo termina antes da publicação | 16 + 12 | 7 | 4 | 9 | 5 | 4 |
| Visibilidade do SET desconhecida | 16 + 12 | 7 | 4 | 11 | 5–11 | 0–6 |

Cada claim produziu uma leitura, três SETs com digests próprios e uma publicação do slot na geração esperada. O quarto expert entrou como preload e foi promovido a demanda. As cinco entradas de fila deram **quatro** entregas físicas simuladas, com os mesmos bytes verificados nos três consumidores. O revisor verifica TID, papel, extensão, conteúdo, geração, promoção e fecho. Reconstitui o caminho crítico e torna gratuitos apenas os nós de entrega na contração. O intervalo READY descreve uma dependência já presente no grafo. Somá-lo à duração das entregas contaria duas vezes trabalho sobreposto.

No terceiro caso, a publicação host ocorre no tick 7 e o consumidor começa no 9. Duas explicações respeitam todas as marcas. Se um requisito independente só fica pronto no tick 9, conceder entrega imediata mantém o fim no tick 11. Se a última dependência é a visibilidade da própria entrega, a contração deixa apenas os três ticks do ramo de cálculo e os dois do consumidor. Para escolher entre os extremos numa implementação assíncrona, falta o evento que identifique **qual dependência o consumidor efetivamente esperou**, incluindo a fence que comprove a visibilidade dos bytes. [Observação proposta para o C291](../packed_prefill/observation.md)

O revisor reabriu os três registos e reproduziu o recibo byte a byte. Três alterações deliberadas dos eventos foram preservadas e rejeitadas: publicação de geração obsoleta, ausência de um fim de SET e segundo claim para uma promoção já satisfeita. Os testes também variaram o cálculo entre 1 e 10 ticks, trocaram TID e digest, recuaram o relógio e alteraram a declaração de cobertura. A fixture cobre uma camada sintética com quatro jobs sem reaproveitamento posterior do slot. O tempo recuperável no prefill natural de 5+148 continua indeterminado. [Contraprovas e respetivos hashes](refutations.json) · [Orçamento do pedido P](../packed_prefill/README.md)

### Reprodução

Para gerar registos novos, usar destinos inexistentes. Os PID/TIDs e a ordem de eventos de workers diferentes no mesmo tick podem mudar entre processos. O revisor autentica a ordem e as identidades de cada execução e compara os resultados da mesma captura.

```sh
D=research/qualification-retake/igpu_resident_rank/request_budget/device/pack_events
python3 -IB "$D/test_events.py"
python3 -IB "$D/run.py" --new-output-dir "$CAPTURE"
H=$(sha256sum "$CAPTURE/receipt.json" | cut -d' ' -f1)
python3 -IB "$D/run.py" --replay-dir "$CAPTURE" --receipt-sha256 "$H" --new-output-dir "$REOPEN"
cmp "$CAPTURE/receipt.json" "$REOPEN/receipt.json"
python3 -IB "$D/test_events.py" --source "$CAPTURE" --receipt-sha256 "$H" --new-output-dir "$FAULTS"
```

SHA-256 do recibo original `2df65466d14bd16bdf35bdfc187ebd0f6e39c798c276aa94a80664660c103ac2` e das três rejeições `4d2db923b4b52e39081a6f1a5e6232a2b1fbbd973a71920838dc6126084e9081`. Para reabrir um arquivo recebido, usar o SHA externo selado no argumento `--receipt-sha256`.
