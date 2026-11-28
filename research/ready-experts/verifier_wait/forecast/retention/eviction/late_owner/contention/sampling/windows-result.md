# As quatro lanes conseguem cumprir os prazos dos consumidores?

**O piso anterior é impossível nos dois processos. A viabilidade da variante continua INCONCLUSIVE.** No caso P106 com os SET pagos, o primeiro horário de 3,350 s para a chamada de 148 deixa **247 790 278 ns de trabalho dos leitores sem lugar**. O fluxo admite interrupção e migração gratuitas e conhece antecipadamente as durações. Em P97 faltam 292 454 152 ns de trabalho ao tentar o correspondente piso de 3,218 s. São défices em tempo somado de workers. [Pré-registo](windows-protocol.md) · [Certificados de fluxo e testes de despacho](evidence-lanes-20261128-r01/windows.json)

| P106, chamada de 148 | Prazo, s | Teste dos quatro leitores | Despacho sem preempção |
|---|---:|---|---|
| SET pago, piso inicial | 3,350 | impossibilidade certificada | 650 de 1 212 gerações atrasadas |
| SET pago, 10 s integrais | 2,795 | o próprio grafo excede o prazo em 555 ms | sem horário |
| SET pago, 10 s com crédito máximo | 3,441 | fluxo completo | 629 de 1 212 atrasadas |
| SET direto nos hits, piso inicial | 3,303 | impossibilidade certificada | 453 de 1 212 atrasadas |
| SET direto nos hits, 10 s integrais | 2,934 | o próprio grafo excede o prazo em 369 ms | sem horário |
| SET direto nos hits, 10 s com crédito máximo | 3,580 | fluxo completo | 273 de 1 212 atrasadas |

As etapas partilham um único conjunto de quatro leitores. O verificador confronta os 1 212 jobs da segunda chamada com o respetivo consumidor e com a geração original. A capacidade agregada por chamada passa mesmo quando uma janela local se encontra saturada. No prazo de P97 para os 10 s integrais, o fluxo passa para os dois modos, mas o despacho por prazo falha em 300 / 186 gerações com SET pago / direto. Uma falha deste despacho conserva a possibilidade de outra ordem. Um fluxo completo admite dividir um único pread ou SET em vários trechos e migrar de lane. Uma implementação precisa de demonstrar uma agenda sem preempção e pagar a contenção e a captura reais. [Bases, comandos e custos](evidence-lanes-20261128-r01/provenance.json)

**Diagnóstico de margem.** Procurámos por busca binária o primeiro nanossegundo em que a capacidade dos quatro leitores chega a todos os consumidores. Com SET pago em P106, a chamada de 148 precisa de pelo menos 3 411 732 143 ns. Um nanossegundo antes faltam dois nanossegundos de trabalho no corte. Face ao piso inicial, a obrigação aumenta 61,948 ms. **Restam só 29,620 ms** mesmo depois de conceder todo o observador. O primeiro final integral teria um piso de 10,617 s. Com SET dos hits gratuito, a margem creditada é 228,760 ms e o primeiro final integral continuaria em pelo menos 10,418 s. Em P97 os mínimos para o primeiro final são 9,616 s e 9,430 s, respetivamente. A pesquisa reproduziu os três prazos e verificou os dois inteiros adjacentes em cada braço. A decisão de investimento mantém os critérios do protocolo original. [Cortes por modo e processo](evidence-margin-20261128-r01/thresholds.json) · [Comandos do diagnóstico](evidence-margin-20261128-r01/provenance.json)

```sh
S=research/ready-experts/verifier_wait/forecast/retention/eviction/late_owner/contention/sampling
python3 -IB "$S/tile_lanes.py" --check "$S/evidence-lanes-20261128-r01/windows.json"
python3 -IB "$S/lane_margin.py" --check "$S/evidence-margin-20261128-r01/thresholds.json"
python3 -IB "$S/test_tile_cost.py"
```
