# O reuso de aquisições do prefill combina com a previsão por token?

A extensão classificou as 892 aquisições em 726 primeiras faltas ausentes de ambas as fontes, 125 presentes apenas à entrada, 38 fornecidas apenas durante a chamada e três nas duas fontes. Os 125 pesos que um espelho de entrada perfeito preservaria somam 1 652 400 000 B de payload distinto. O melhor primeiro final passaria em P97, com 9,926 s no extremo favorável, e falharia em P106 mesmo no extremo favorável, com 10,005 s. Os extremos conservadores chegam a 10,151 / 10,230 s. **INCONCLUSIVE para o espelho ilimitado.** Uma agenda finita também teria de pagar a captura. [Protocolo da entrada](entry.md) · [Contagens por tier e braços](evidence-entry-20261128-r01/receipt.json) · [Teste físico das 726 aquisições](io-protocol.md)

**NO_GO no nominal.** Depois dos 371 acertos do banco secundário, o prefill ainda exige 892 leituras. Destas, 41 podem receber uma cópia fornecida anteriormente dentro do mesmo retorno externo. Mesmo com futuro conhecido, memória ilimitada, captura gratuita e todo o crédito das adjacências originais, essa oportunidade só retira 94,374 ms em P97 e 88,444 ms em P106. A previsão por ID no decode precisava de 386–713 ms. O primeiro final da combinação mais favorável fica em **10,292–10,625 s**. [Protocolo congelado](protocol.md) · [Testemunhas, todos os braços e orçamentos](evidence-20261128-r01/receipt.json)

| Agenda | Leituras evitadas / 892 | Prefill P97 / P106 | Primeiro final nos dois journals |
|---|---:|---:|---:|
| Sem reuso extra | 0 | 4,104 / 4,197 s | 10,386–10,713 s |
| Duas cópias por estágio, recência causal | 0 | 4,104 / 4,197 s | 10,386–10,713 s |
| Duas por estágio, seleção offline com o máximo de acertos | 8 | 4,093 / 4,186 s | 10,375–10,702 s |
| Todas as aquisições reutilizáveis, cópias ilimitadas e adjacências integralmente creditadas | 41 | 4,010 / 4,109 s | 10,292–10,625 s |

O resultado é **TRACE_DERIVED** a 4,5 GB/s. A agenda de recência exigiria guardar 16 695 849 600 B nas 1 263 capturas, com 52 887 552 B adicionais para quatro lugares. Mesmo a custo zero, o braço causal excede o limite. O pico dos intervalos escolhidos para os oito acertos é de dois por estágio. Selecionar os 41 exige picos de 20 e 15 nos estágios respetivos. A prova pela capacidade só maximiza o número de leituras evitáveis. A prova temporal mais generosa recalcula o percurso das duas tiles em pipeline, mantém os três SET e torna os créditos anteriores monotónicos para cobrir também qualquer subconjunto. A mudança só pode poupar aquisições repetidas de pesos fornecidos dentro do mesmo retorno. As 851 restantes admitem outras origens, incluindo pesos já presentes à entrada. [Agenda e verificador](replay.py)

O controlo sem reuso reproduziu os dois preços de prefill ao nanossegundo. As quatro agendas chegam ao decode com os mesmos dois bancos, slots e gerações. O decode projetado dos 47 IDs varia entre 6,475 e 6,544 s. O tempo restante até ao primeiro final decide o resultado. O ensaio é sem modelo, com zero acessos a pesos ou GPU. Duas execuções na árvore limpa `1b33ad2634ed18885c2429b2d0cfd2cab10d1261` deram o mesmo recibo SHA-256 `4606ac9a6ea424537f85df4037b58ac73054580b6289f72719d7e8d987ba4e61`, em 0,50 e 0,52 s, máximos de 37 524 e 37 352 KiB de RSS. [Versão, comandos e orçamento](evidence-20261128-r01/provenance.json)

```sh
d=research/ready-experts/verifier_wait/forecast/retention
python3 -IB "$d/test_replay.py"
python3 -IB "$d/replay.py" --check "$d/evidence-20261128-r01/receipt.json"
```
