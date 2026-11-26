# O que acrescenta um banco adquirido em T1 aos quatro caminhos de decode?

**Com as 35 recuperações demonstradas, nenhum dos três bancos leva os quatro caminhos já escolhidos aos dois alvos, mesmo na hipótese favorável de exposição integral.** Com todas as 230 recargas gratuitas e o menor preço individual observado entre braços, há margem condicional para o banco de recência ou o misto. No caminho de maior débito, o crédito necessário é respetivamente 33,5886% e 51,0730% do preço das leituras elegíveis nos passos seriais. A capacidade de realizar as 230 recuperações e os custos de adquirir e entregar a cache ficam em aberto. O resultado é TRACE_DERIVED. [Protocolo](bank-protocol.md) · [Todos os valores por banco e caminho](bank-result.json) · [Caminhos sem o banco](envelope.md)

| Banco selado em T1 | Aquisição em T1 (GB) | Reservas de prefill cobertas | Em comum com 35 / união | Em comum com 230 / união | Hits de decode nos passos preservados, caminho mais rápido |
|---|---:|---:|---:|---:|---:|
| Vazio | 0 | 0 | 0 / 35 | 0 / 230 | 0 |
| Últimas 353 vítimas | 59,566 | 155 | 3 / 187 | 24 / 361 | 111 |
| 176 por frequência e restantes por recência | 58,138 | 223 | 9 / 249 | 43 / 410 | 73 |
| Frequência do prefill de T1 | 20,477 | 297 | 14 / 318 | 69 / 458 | 33 |

Uma reserva é uma geração completa do journal. Os dois traces reconciliaram 1 263 no prefill e 1 091 no decode. Entre os 172 hits de decode do banco de recência, 61 pertencem a calls substituídas no caminho de maior débito. Os 111 elegíveis ocorrem antes do primeiro final nesse caminho. Para o banco de frequência, 43 dos 76 hits ficam nas calls substituídas e restam 33. Conceder o banco a todos os passos iniciais e somar também o ganho dos blocos teria criado crédito sobre a mesma transição. [Políticas e custos de aquisição anteriormente congelados](../../../../../../../../../../../../igpu_resident_rank/request_budget/device/pack_native/natural_trace/prefill_retention/mixed_bank/README.md)

| Preço das chamadas seriais de 193 | Recuperações | Recência · caminho primeiro final / decode | Misto · primeiro final / decode | Frequência |
|---|---|---|---|---|
| SERIAL contemporâneo | 35 ou 230 | Sem caminho entre os dois | Sem caminho entre os dois | Sem caminho entre os dois |
| Menor visto entre os três braços | 35 | Sem caminho entre os dois | Sem caminho entre os dois | Sem caminho entre os dois |
| Menor visto entre os três braços | 230 | 62,4441% / 33,5886% | 95,3094% / 51,0730% | Sem caminho entre os dois |

Nos quatro caminhos e com as 35 recuperações, o caso de frequência que mais se aproximou dos 10 s ainda precisava de 17,901 ms até ao primeiro final e 89,424 ms no decode. No outro caminho, os défices foram 65,506 e 12,585 ms. São combinações diferentes. Uma alteração da cache pode mudar qual agenda é melhor. Para decidir o valor das 35 antes de uma fixture física, é necessário voltar a escolher o caminho com a cache já contabilizada. O banco vazio reproduziu os quatro saldos da parte 194. Os dois cenários favoráveis com 230 liberam somente o estudo de viabilidade neste modelo de custos.

O cálculo dá às leituras eliminadas no prefill crédito integral sobre o piso de 14 623 408 128 B de SERIAL. O tempo disponível para as restantes aumenta apenas com o ganho de decode ocorrido antes da amostra 45. Cada passo preservado tem o seu próprio teto de duração. O ganho posterior à amostra conta apenas para o débito. Os 353 experts ocupam 4 666 377 600 B de payload, ou 4,346 GiB. Somar esse payload ao pico do processo SERIAL dá 20 453 672 320 B face ao cap de 21 474 836 480 B. Restam 1 021 164 160 B para efeitos de alocação, temporários e variação de pico nessa estimativa. As cópias, o custo do primeiro turno, o estado à entrada de cada bloco e a duração do pedido com banco ainda não foram medidos.

Protocolo e código em `cf63739b842c6ec21d1bd21fd61c3c0aa4cf7f86`. As duas execuções duraram 4,815 e 4,830 s, com 120,3 e 116,4 MiB de pico, zero swap, GPU ou novos pedidos. O resultado idêntico tem SHA-256 `faff519fbe22d9a50455247de29866f8743b448cb0743b1309082fecc565fd2d`. O arquivo 195 contém quatro ficheiros e 70 294 B. [Recibo](../../../../../../../../../../../../private_archive/part-195.json) · [Verificador](bank.py)

```sh
python3 -IB "$STUDY/bank.py" --archive "$AR" \
  --family "$AR/part-193/tesy-c281-context-http-20261126-r02" \
  --capture "$AR/part-29/tesy-natural-ids-capture-20261125-r01" \
  --verified "$AR/part-29/tesy-natural-ids-verified-20261125-r01" \
  --plan "$AR/part-177/tesy-packed-causal-plan-20261126-r03" \
  --commit cf63739b842c6ec21d1bd21fd61c3c0aa4cf7f86 --new-output-dir "$NEW"
```
