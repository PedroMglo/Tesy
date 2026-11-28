# Que parte do ganho exigiria sobrepor duas fatias?

**INCONCLUSIVE para construir o executor de duas fatias e NO_GO para uma reescrita integral com esta evidência.** A espera entre a frente de uma fatia e a cauda da anterior vale 0,816 / 0,815 s no melhor cenário com SET pago. Ao alterar só essa dependência, o primeiro conteúdo final passa de 10,359 para 9,543 s em P97 e de 11,369 para **10,555 s** em P106. São valores condicionais calculados com os preços do portátil. [Protocolo congelado](pipeline-protocol.md) · [Todas as fases nos dois layouts e velocidades da ligação](evidence-pipeline-20261128-r01/pipeline.json)

| Layout aprendido e preços das leituras | Série, P97 / P106, s | Duas fatias, P97 / P106, s | Duas fatias com crédito do observador em P106, s |
|---|---:|---:|---:|
| Sem desconto, SET pago | 11,834 / 12,826 | 10,843 / 11,806 | 11,160 |
| Redução baixa, SET pago | 11,056 / 12,057 | 10,165 / 11,154 | 10,508 |
| Redução alta, SET pago | 10,359 / 11,369 | 9,543 / 10,555 | **9,908** |
| Redução alta, SET dos hits gratuito | 10,172 / 11,167 | 9,370 / 10,369 | **9,722** |

**O que tem de caber.** Mesmo na linha de redução alta e SET pago, P106 só atravessa os 10 s se forem efetivamente retirados pelo menos 554,861 dos 646,428 ms anteriores ao stream. Conceder esse intervalo todo deixa **91,567 ms** para qualquer espera adicional no caminho crítico. Oferecer também o SET dos hits aumenta esse máximo para **277,627 ms**. O decode com SET pago no extremo alto dá 6,279 / 6,544 s para 47 IDs. Tanto 4,5 como 8 GB/s deram aqui o mesmo preço do pedido. A energia, prontidão dos novos destinos, captura das vítimas e paridade do primeiro decode no executor proposto continuam por medir.

As 2 354 gerações repartem-se por 674 hits, 221 misses em adjacências e 1 459 misses isolados. Descartámos 0,572 / 0,552 s de crédito em tempo somado dos workers que recairia sobre READ adjacentes já gratuitos. Aplicaram-se 3,329 / 3,320 s de crédito em tempo dos workers isolados. Nenhuma interseção usada misturou consumidores diferentes. O limite por chamada cobra o trabalho somado dividido por quatro e o payload frio na ligação. Resta verificar se os mesmos quatro workers cabem também nos intervalos conflitantes de cada consumidor quando a CPU e a GPU avançam em simultâneo. [Recibos das leituras](three-result.md) · [Unidade e comandos](evidence-pipeline-20261128-r01/provenance.json)

O verificador correu em 3,68 s com 143 420 KiB de pico de RSS, sem carregar pesos nem usar a GPU. A cadência dentro de cada estágio, as taxas transferidas e a aquisição inicial do banco são hipóteses. A comparação mantém a geometria e os relógios dos registos P97 e P106 e oferece as mesmas dispensas à execução em série e à sobreposta.

```sh
S=research/ready-experts/verifier_wait/forecast/retention/eviction/late_owner/contention/sampling
python3 -IB "$S/tile_cost.py" --check "$S/evidence-pipeline-20261128-r01/pipeline.json"
python3 -IB "$S/test_tile_cost.py"
```
