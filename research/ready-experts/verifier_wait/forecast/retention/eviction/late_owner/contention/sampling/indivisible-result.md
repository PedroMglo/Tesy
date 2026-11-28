# Manter a leitura e os três SET no mesmo worker muda a decisão

**NO_GO para sobrepor duas tiles com as cópias atuais, aos preços aferidos neste portátil. INCONCLUSIVE se os hits puderem chegar diretamente ao consumidor.** Com todos os créditos de cliente em P106, a recorrência das duas fatias ainda aparenta entregar o primeiro conteúdo em 9,990 s. Ao exigir que os mesmos quatro workers sirvam cada consumidor até ao seu prazo, o corte deixa **88 541 298 ns de trabalho sem capacidade**. Estes workers já dispunham de migração e preempção gratuitas entre as janelas. O horário real com os três SET pagos não pode caber nesses preços e prazos. [Protocolo](indivisible-protocol.md) · [Grupos, preços e certificados por braço](evidence-indivisible-20261128-r01/service.json)

| Processo e entrega dos hits | Primeiro final integral, s | Primeiro final com crédito, s | Capacidade nos prazos com crédito |
|---|---:|---:|---|
| P97, SET pago | 9,624 | 9,624 | passa o fluxo, a ordem tentada falha |
| P106, SET pago | 10,637 | 9,990 | **impossível mesmo no fluxo** |
| P97, SET gratuito | 9,472 | 9,472 | passa o fluxo, a ordem tentada falha |
| P106, SET gratuito | 10,473 | 9,826 | passa o fluxo, a ordem tentada falha |

Os tempos da tabela são os pisos da recorrência antes de testar a capacidade local no prazo dos 10 s. Em P106 a heurística com entrega direta atrasa 248 de 1 212 gerações no prazo creditado. O fluxo só comprova a possibilidade de dividir o trabalho nessa relaxação. Dar custo zero aos SET dos hits inclui os destinos na GPU. O decode de 47 IDs com SET pago continua em 6,279 / 6,544 s e com entrega direta em 6,154 / 6,409 s. A reserva e as capturas permanecem gratuitas.

O solver verificou 410 regiões por processo e modo. Fechou exatamente 398 / 397 em P97 / P106 com SET pago e 406 / 407 com entrega direta. Em todas as restantes usou o limite inferior certificado. Uma atribuição local completa verifica o limite superior em cada caso. A paragem por orçamento de procura conserva o intervalo. A execução demorou 5,09 s e usou 195 520 KiB de pico, sem GPU nem pesos. [Proveniência e reprodução](evidence-indivisible-20261128-r01/provenance.json) · [Margem anterior com divisão livre dos jobs](windows-result.md)

```sh
S=research/ready-experts/verifier_wait/forecast/retention/eviction/late_owner/contention/sampling
python3 -IB "$S/indivisible.py" --check "$S/evidence-indivisible-20261128-r01/service.json"
```
