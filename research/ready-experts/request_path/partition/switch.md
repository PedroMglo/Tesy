# O ganho sobrevive se ligarmos o filtro apenas no prefill?

**NO_GO para ligar o filtro só durante esta fase. GO para a fixture dos onze pesos que já se encontravam na camada.** Na chamada natural de 148, mudar de política a partir da residência efetiva custa 700 leituras, mais 268 para devolver os membros do controlo no primeiro decode. O próprio serviço contínuo faz 532. O ganho aparente de 31 leituras da experiência anterior dependia de chegar à chamada com outro estado. Nos perfis fornecidos, a reposição custa mais do que se poupou nos dois casos. [Pré-registo](switch-protocol.md) · [Recibo e fases dos dois clientes](evidence-switch-20261128-r01/decision.json)

| Prefill CPU com o mesmo estado de saída | Controlo | Filtro · procura + reposição | Mínimo sem limite de memória | Oráculo das waves com 1 212 frames + 40 temporários |
|---|---:|---:|---:|---:|
| Natural, exclusivamente 148 | 532 | 700 + 268 | 405 | 405 + 40 |
| Nominal153 fornecido | 582 | 511 + 255 | 484 | 484 + 40 |
| Code153 fornecido | 1 475 | 1 378 + 534 | 998 | 998 + 40 |

Na conversa natural, tanto a entrada da call de 148 como a saída tinham 1 252 membros CPU. A entrada nos dois fornecidos tinha 1 000 e a saída 1 252. A escolha com conhecimento de toda a fase representa um potencial de **87, 58 e 437 leituras**, respetivamente, mesmo cobrando a reposição mínima dentro desse contrato. A política precisaria de antecipar a utilidade de pesos para routers que ainda não executaram. [Estados e testemunha reproduzível](evidence-switch-20261128-r01/witness.json.gz)

Se o mecanismo restaurar os membros do primário e do banco ao fim de cada visita, das 532 leituras naturais pelo menos **521** são obrigatórias. As restantes 11 encontram-se em nove das 125 visitas CPU. Todos os 11 pesos já estavam disponíveis à entrada da visita ou tinham sido pedidos nela, e o primeiro consumidor é identificável. No replay da agenda observada de quatro workers, dar gratuitamente os respetivos READ e SET, com os hits do banco já descontados, poupa **23,926 ms em P97 e 8,419 ms em P106** até ao primeiro conteúdo e à conclusão válida. As duas ordens compatíveis em cada journal dão o mesmo valor. O relógio do decode fica igual. O orçamento para mais coordenação exposta e para qualquer cópia no caso mais exigente é de 8,419 ms por pedido. Estes tempos são TRACE_DERIVED a preços fixos. [Protocolo da fixture com os pesos](visit-protocol.md)

Código `9c517017c7afb988f61b387d79c399f1cb192701`, árvore `3b7744dac799c7ffe6c22220c699c7a9b8b7f58f`. A aquisição e o replay demoraram 8,66 s e atingiram 270 664 KiB de RSS. Não carregaram o modelo.

```sh
p=research/ready-experts/request_path/partition
python3 -IB "$p/test_switch.py"
python3 -IB "$p/switch.py" --check "$p/evidence-switch-20261128-r01"
python3 -IB "$p/switch.py" --archive "$TESY_ARCHIVE" --c294-raw "$TESY_C294_RAW" --new "$WORK/switch"
```
