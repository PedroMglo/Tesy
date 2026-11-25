# Antecipar apenas o prefill CPU não fecha os 10 s do P106

**Mesmo concedendo previsão perfeita e libertação tão cedo quanto o grafo permite, antecipar só as camadas CPU1–24 de prefill deixa o primeiro final P106 em pelo menos 10,349 s.** Falta um ganho independente de **349,362 ms antes da primeira peça**, mais o preço exposto da implementação. Se o sinal só estiver disponível no RANKS observado, o piso sobe para **11,644 s** e faltam **1 644,355 ms**. No P97 o cenário mais cedo fica aquém de 10 s; com RANKS observado, excede o alvo em 438,106 ms. Os dois relógios pertencem a cada pedido, e o FREQ353 selado no T1 de P106 é aplicado ao P97 como sensibilidade após verificar as identidades. [Resultados dos três modos](receipt.json) · [Pré-registo](protocol.md)

| Pedido | Início elegível | Só rota local, primeiro final / decode (s) | +1 só prefill CPU, primeiro final / decode (s) | +1 em todas as fases e destinos, primeiro final / decode (s) |
|---|---|---:|---:|---:|
| P97 | RANKS observado | 11,256 / 5,260 | **10,438 / 5,260** | 9,240 / 4,310 |
| P97 | Fronteira anterior | 9,651 / 4,272 | **9,286 / 4,272** | 8,685 / 3,879 |
| P106 | RANKS observado | 12,475 / 5,558 | **11,644 / 5,558** | 10,326 / 4,488 |
| P106 | Fronteira anterior | 10,702 / 4,446 | **10,349 / 4,446** | 9,738 / 4,047 |

A rota local pode lançar entregas depois de saber os experts verdadeiros. No cenário anterior, concede-se essa mesma vantagem a todas as regiões, incluindo os destinos CUDA e os 46 passos de decode que não recebem previsões no modo CPU. O controlo local fixa assim a mesma suposição de disponibilidade. Todos os valores são pisos condicionais sob 4,5 GB/s úteis, um link CPU/CUDA, os mesmos SET precificados, e custos de previsão e de serviço do banco oferecidos. No P106 o recorte CPU desloca o piso de primeiro final em **831,119 ms** no RANKS e **353,017 ms** na fronteira anterior, em relação ao controlo local. Isto mede a diferença entre dois limites. No braço natural observado sem antecipação, o primeiro final e o decode demoraram 19,529 s e 9,214 s. [Todos os serviços do pack e os SET](../README.md) · [Relógio do cliente](../../README.md)

**Qual segundo mecanismo seria necessário?** Os 349,362/1 644,355 ms têm de vir do prefill ou das 44 avaliações anteriores à primeira peça. Reduzir o trabalho das duas últimas avaliações não paga esse défice. Se o ganho adicional vier *inteiramente* do decode anterior à primeira peça, em cima destes pisos otimistas, o decode total P106 terá de cair de 4,446 para no máximo 4,097 s na fronteira anterior, ou de 5,558 para no máximo 3,913 s no RANKS. Isto equivale a pelo menos **11,473 / 12,011 tok/s** no denominador contratual de 47. Os pisos de decode deste recorte já são compatíveis com 47/6 s; a margem residual de 3 387,298 / 2 275,801 ms nesse relógio não paga custos que chegam antes do primeiro final.

A população CPU1–24 contém 762 reservas de prefill, das quais 594 usam o pack e 168 o banco. A execução densa de uma projeção por camada e posição teria 3 672 pares linha/destino, **1 353 646 080 MAC**, além de normalização, seleção e eventuais cópias. O crivo oferece quatro previsões perfeitas por tile/destino e disputa um único recurso com as restantes cargas. O decoder e o GPU mantêm a mesma autoridade e agenda do controlo local; o verificador exige igualdade dos dois trechos de decode em bytes, suporte temporal e pisos. Um produtor real com fila auxiliar terá de proteger o consumidor, os slots e a memória de staging no carry, e cobrar a contenção, o desperdício e as transferências ainda em voo. O dado C292 de 421 chegadas condicionais para 562 ofertas CPU sustenta testar essa entrega em isolamento; não prova que a taxa ou os prazos sejam os do pedido natural. [Emissão medida no C292](../../../../../../../../../../router_lookahead/observation/target/numeric/windows/README.md)

### Reprodução

Protocolo `6cf0b9ca`, código `8ac74948`. Dois testes cobrem a máscara de fase e destino e a partilha de uma ligação. As duas reanálises, lançadas após o fecho da fixture 5/20, produziram 16 066 B idênticos, SHA-256 `6e70b019662cfee1b20d81879b4050803a9beedda7be9663190b758fee146352`. Duração 8,17/8,20 s; RSS 64 588/64 668 KiB. Cada uma revalida os 2 354 jobs originais. [Código e condições de rejeição](screen.py) · [Testes](test_screen.py)

```sh
python3 -IB test_screen.py
nice -n 10 taskset -c 4 timeout 90 prlimit --as=536870912 --cpu=90 -- \
  python3 -IB screen.py --archive "$PARTS" --backend "$C291" --new-output-dir "$FRESH/r01"
nice -n 10 taskset -c 4 timeout 90 prlimit --as=536870912 --cpu=90 -- \
  python3 -IB screen.py --archive "$PARTS" --backend "$C291" --new-output-dir "$FRESH/r02"
cmp receipt.json "$FRESH/r01/receipt.json" && cmp receipt.json "$FRESH/r02/receipt.json"
```
