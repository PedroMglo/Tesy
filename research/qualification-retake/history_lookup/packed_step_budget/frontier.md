# Quanto podem custar em conjunto o prefill e a verificação?

**CONDICIONAL nas duas conversas nominais com pack.** Para chegar ao primeiro final em 10 s mantendo o restante trabalho exposto, o prefill completo e as dez verificações anteriores a esse frame têm juntos **5,376 s em R/O/P e 5,504 s em P/O/R**. O decode completo tem onze verificações. As 23 chamadas AR sem proposta conservam os seus custos por posição. A 6 tok/s, o limite médio para as onze foi 292,607 e 304,319 ms. A décima primeira cai depois do primeiro final. [Custos na ordem real dos tokens](README.md) · [Cálculo reproduzível](frontier.json)

| Condição para o pedido de 153 tokens | R/O/P | P/O/R |
| --- | ---: | ---: |
| Média máxima das dez verificações com 16,699 GB pagos no prefill a 4,5 GB/s e restante trabalho do prefill inteiramente sobreposto | 166,462 ms | 179,264 ms |
| Prefill disponível se essas verificações custarem 200 ms em média | 3,376 s | 3,504 s |
| Mínimo de leituras inteiras, entre 1 263, a retirar dessa janela ou evitar nesse cenário | 115 | 71 |

P97 e P106 mediram 16 699 244 544 B devolvidos pelo descritor do pack no prefill, em 1 263 leituras de quatro workers. A união de parede com pelo menos uma leitura em curso foi 6,189 e 6,228 s. Se essa ocupação se mantiver dentro do prefill dos pedidos de produto, mesmo verificações gratuitas deixam um défice de **0,685–0,853 s** nas quatro combinações entre os dois diagnósticos e as duas ordens. As janelas de diagnóstico e de produto pertencem a execuções diferentes. Os 4,5 GB/s são uma hipótese de serviço e os bytes medidos pertencem ao descritor. [Intervalos dos READ, bytes devolvidos e worker-tempo](../../igpu_resident_rank/request_budget/device/pack_native/natural_trace/release/lookahead2/decode/all_prefill/bandwidth/README.md)

O cálculo subtrai do alvo o primeiro final projetado com as propostas gratuitas e volta a somar o prefill observado. Esse saldo é o limite para o novo prefill mais o custo integrado das dez verificações, incluindo lookup, desperdício, rejeição e limpeza que atrasem o frame. A verificação do orçamento completo de decode continua independente. A reprodução usa os dois marcadores textuais de produção da amostra 45, preserva a cauda e só credita trabalho que a mudança consiga retirar antes desse frame. Redistribuir duração entre cliente e servidor ou mudar o padrão de propostas exige novos relógios de produto.

```sh
python3 research/qualification-retake/history_lookup/packed_step_budget/frontier.py \
  --new-output-dir "$NEW_RESULT"
```
