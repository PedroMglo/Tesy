# Custo da conversa de referência no stock E10

**NO_GO para gastar 30 minutos na geração natural de referência em E10 segundo a triagem congelada.** O stock executou os 121 IDs oficiais de Aster num processo novo, com SWA completa, amostragem greedy e limite de oito tokens. Os sete passos posteriores ao primeiro token demoraram 1,938–4,346 s, com média de 2,825 s. Para reproduzir a quantidade histórica de trabalho dentro do orçamento caberiam 1,906 s por passo. Uma conversa com outra trajetória pode ter quantidades e custos diferentes. [Protocolo](protocol.md) · [Recibo físico](physical-r1/receipt.json)

| Componente medida ou estimada | Valor | Âmbito |
|---|---:|---|
| Prefill T1 stock | 81,438 s | MEDIDO, 121 IDs reais, cache fria da slot, estado inicial da page cache desconhecido |
| Oito tokens com sete passos posteriores | 19,774 s | MEDIDO pelo servidor no pedido T1. O primeiro token usa os logits do prefill |
| Pedido T1 completo | 101,236 s | MEDIDO no cliente até ao terminal nativo |
| Prefill usado como aproximação de T2 | 211,257 s | MEDIDO noutro processo E10 com 122 tokens fixados e 313 novos. A trajetória natural de T1 pode mudar essa entrada |
| Custos de cliente além das fases, dois pedidos | 0,032 s | Diferenças observadas entre relógios em cada processo |
| Custo dos 791 passos posteriores nos dois turnos | 25,54 / 37,24 / 57,30 min | ESTIMADO se cada passo custasse o mínimo, a média ou o máximo dos sete |
| Tempo total de referência para os dois pedidos | 30,42 / 42,12 / 62,17 min | ESTIMADO para as quantidades históricas de 341 e 452 saídas e 292,727 s fixos |

O intervalo resulta de sete diferenças consecutivas nos relógios do servidor. É uma análise de sensibilidade. A margem do cenário mais rápido é de 25,33 s sobre os 1800 s previstos. O elo mais fraco é extrapolar os primeiros sete passos para todas as posições posteriores. O caso de código, M4 e o conteúdo funcional de Aster mantêm-se nos próprios protocolos.

O ensaio usou o mesmo stock do teste de split, em checkout limpa c421e86f11a8579237625362d47e0c7b1561719e. O pré-inventário sem modelo passou. Uma nova C118 precedeu o arranque no portátil. A unidade demorou 192,360 s com inventário e encerramento. O pico do cgroup foi de 10 203 283 456 B, com swap zero e zero OOM, e o da GPU foi de 4 382 MiB. O cgroup contabilizou 299 465 220 096 B de leituras no dispositivo interno em toda a vida do servidor. A energia isolada permanece desconhecida. O raw privado conserva os oito endpoints, pedidos, resposta SSE e monitor. O recibo físico tem SHA-256 b26808e96d641a78d132ba44804957be69b2e66f3adbbe23ab6eb4173c188e2d. [Precheck](precheck-r1/receipt.json) · [Comparação de split](../aster_split/README.md)

Para reproduzir, usar a mesma chamada do perfil E10 em diretórios exclusivos, com a entrada aster_budget/probe.py, os resultados históricos e os argumentos --split-receipt e --split-sha256 correspondentes à sonda anterior. Os testes de CI cobrem os relógios incompletos e o terminal EOS antecipado sem carregar pesos. [Entrada do supervisor e cgroup](../aster_full_ready/README.md)
