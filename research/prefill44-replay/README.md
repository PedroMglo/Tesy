# Replay do prefill C163 com 44 slots

**GO para usar C163 como fixture lógica da política de residência.** A partir do snapshot warm e das rotas do target, o replay escolheu corretamente todas as 899 vítimas em cada braço e chegou ao estado observado no fim de 5+148. Usou a ordem observada dos quatro workers. Não se mediu um ganho de latência. [Pré-registo](protocol.md) · [Recibo dos dois braços](evidence/receipt.json)

| C163 | Rotas | Demands | Vítimas / reservas | Preloads | Enqueues / stale | Barreiras / slots na espera | Publicações |
|---|---:|---:|---:|---:|---:|---:|---:|
| ON-1 | 212 | 3 807 | 899 / 901 | 277 | 1 104 / 203 | 211 / 3 284 | 901 |
| ON-2 | 212 | 3 807 | 899 / 901 | 277 | 1 105 / 204 | 210 / 3 282 | 901 |

Cada braço tem 37 remaps e 1 120 conclusões de wave. Na call 9, as camadas 0–34 recebem cinco posições e a camada 35 calcula uma linha. Na call 10, as camadas 0–34 percorrem 32+32+32+32+20. A camada 35 recebe uma linha no último tile. O journal preserva as waves vazias que ainda produzem IDs de parking. O auditor consome as rotas na ordem por token para reconstruir a ordem de primeiro uso, a divisão por waves e a recência de cada expert. Na admissão, aplica as exclusões de residentes protegidos e slots em carregamento. Entre as restantes, escolhe primeiro uma slot vazia, depois por hotness, recência e índice físico. A leitura do evento EVICT serve para verificar a escolha calculada. [Controlador](replay.py) · [Fonte e identidade C156](../../results/c163-instrumentation-overhead-20260930T1145Z/protocol.json)

O teste compara as componentes de planeamento com o snapshot final de cada uma das 36 camadas, incluindo os 15 vetores, contador de utilização, slots e capacidade, número e próxima wave. Confere o relógio global de chamadas, decaimento, identificador do trabalho e ausência de trabalho pendente em ambas as fronteiras. Reproduz também as gerações de que depende cada barreira, a ordem FIFO e as publicações por worker. Os estados de parking intermédios são reconstruídos da fonte e das rotas. O journal fornece os limites de wave e os snapshots fornecem o estado de parking nas fronteiras capturadas. Os dados provêm do mesmo workload nominal em dois processos. O probe C-API usa 44 slots por camada. A reprodução para o servidor C135 de 40 slots, os custos das faltas novas e as proteções de produto continuam em aberto. [Campos do snapshot](../../tools/c152_snapshot_read.py) · [Gate de journal](../../tools/c152_journal_validate.py)

Quatro fixtures model-free validam a seleção de vítima, exclusões, parking por rank, waves vazias e o decaimento. Cinco mutações dirigidas de C163-ON-1 divergiram como esperado ao trocar a vítima, a ordem de routing ou os campos de parking, recência e hotness do snapshot final. Os testes não alteram os originais. [Fixtures](test_replay.py) · [Falhas injetadas](fault_checks.py)

## Reprodução

Na raiz do Tesy, apontar TESY_C163_RAW para a pasta histórica raw. Cada execução exige um destino novo.

```sh
python3 -m unittest discover -s research/prefill44-replay
out=$(mktemp -d)
python3 research/prefill44-replay/study.py --raw-dir "$TESY_C163_RAW" --new-output-dir "$out/replay"
```

O manifesto e o protocolo históricos estão pinados por SHA. Os dez ficheiros consumidos nos dois braços foram conferidos por tamanho e SHA-256. Fonte do logger 0fd9de9cf08a0ee6f6fdaad0328efa221ada5c7b, árvore f21dd2218eeb90677870e9000884935fd4b233f6. Base integrada 293f5b184da9439771cce361cd33fc4068d749f4. Os três ensaios locais duraram 0,78, 1,28 e 1,26 s, com pico de 127 056 KiB. O primeiro confirmou os controlos, o segundo acrescentou as mutações e o terceiro reproduziu o recibo do segundo após a formatação. As execuções consumiram 3,32 s do orçamento de 120 s. A reprodução final a partir da branch coincidiu byte a byte e consumiu 1,30 s, para um total de 4,62 s nas quatro execuções. Energia sem instrumentação. Uso de GPU e modelos zero. Recibo SHA-256 f27d76452439cb31cf1cb25b49c3d2d2c85003602ceb0796e669ac0457817965. [Manifesto histórico](../../results/c163-instrumentation-overhead-20260930T1145Z/raw-manifest.json)

O próximo discriminante poderá comparar a política original e a pré-proteção dos residentes da wave corrente no mesmo estado inicial de 44 slots. Deverá contar as faltas introduzidas, além das eliminadas, e os efeitos no estado entregue ao primeiro decode. Uma agenda contrafactual precisa de definir o serviço dos novos pedidos e os efeitos de contenção para lhes atribuir tempo. A avaliação de 40 slots exigirá a sua própria identificação de estado, rotas e validadores.
