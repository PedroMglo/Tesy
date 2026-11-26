# Quanto tempo tem de libertar o serviço do prefill com o pack?

**No T2 observado, mesmo que o decode passe para 6 tok/s e toda a poupança chegue ao cliente antes do primeiro conteúdo final, uma intervenção limitada às leituras e aos SETs do prefill tem de poupar 7,154 dos 9,554 s.** A 8 tok/s o requisito desce para 5,195 s. O P mediu os bytes do dispositivo e os relógios do pedido. Falta saber quantos segundos as entregas dos experts acrescentaram ao caminho crítico nas chamadas de 5 e 148 tokens. O passo discriminante é uma observação dessas entregas no cliente natural com o pack. [Formato e verificação da observação](observation.md)

O braço P conservou 2044 entradas de contexto, produziu 47 saídas em 8,784071 s de decode e entregou o primeiro conteúdo final ao cliente em 18,104271781 s. O primeiro token sai do prefill. Há 46 avaliações seguintes, 44 delas entre a primeira amostra e a amostra 45, que inicia o conteúdo final. São 8,539603 s no relógio do produtor até esse corte e 0,244467 s na cauda. O contrato de débito usa as **47 saídas** e o tempo integral do decode. [Observação original e relógios](../README.md)

| Taxa contratual (saídas/s) | Tempo das 47 saídas (s) | Ganho de decode creditado antes do final (s) | Prefill admissível (s) | Ganho necessário no prefill (s) | GB/s no prefill se todos os bytes atravessarem | GB/s no decode na mesma hipótese |
|---:|---:|---:|---:|---:|---:|---:|
| 5,351 medida | 8,784 | 0 | 1,449 | 8,104 | 11,342–11,559 | 1,626–1,660 |
| 6 | 7,833 | 0,951 | 2,400 | 7,154 | 6,849–6,980 | 1,823–1,861 |
| 8 | 5,875 | 2,909 | 4,358 | 5,195 | 3,772–3,844 | 2,431–2,482 |
| 10 | 4,700 | 4,084 | 5,533 | 4,020 | 2,971–3,027 | 3,038–3,102 |

Seja **x** o ganho líquido de decode em segundos que antecipa o primeiro conteúdo final, conservando o restante trabalho exterior ao prefill e a resposta. Para qualquer x, o prefill dispõe de **1,449280219 + x** segundos e precisa de poupar **max(0, 8,104271781 − x)** segundos. A primeira linha mantém o decode medido e falha a meta simultânea de 6. As outras três creditam todo o ganho de decode antes do final, com cauda inalterada. O recibo fornece ainda orçamentos creditando metade e zero. São sensibilidades conservadoras ao crédito demonstrado. Uma decomposição temporal de uma execução teria também de caber na cauda efetivamente observada. Como convenção alternativa, contar **46 avaliações a 6 avaliações por segundo** significa 46/6 s no decode e 6,1304 **saídas**/s. O prefill teria 2,567 s, exigindo 6,404–6,527 GB/s. Essa conta pertence a outra taxa de produto. [Recibo com todas as sensibilidades](receipt.json)

### O que dizem os bytes

O cgroup submeteu entre **16 437 952 512 e 16 752 132 096 B** no prefill e entre **14 279 639 040 e 14 580 596 736 B** no decode. Os contadores globais do namespace registaram, separadamente, 32 123 008–32 718 336 setores de leitura de 512 B no prefill e 27 890 768–28 484 048 no decode. As bandas da tabela dividem apenas os bytes do cgroup pelo tempo da fase. Para uma banda B e uma fração f do volume V que tenha de atravessar a ligação dentro da fase, a condição é fV ≤ B × tempo admissível. O P deixou f por identificar. [Intervalos e método da parte 88](../phases/README.md)

| Taxa (saídas/s) | Saldo do **prefill** a 4,5 GB/s (s) | Saldo do **prefill** a 8 GB/s (s) |
|---:|---:|---:|
| 5,351 | −2,204 | −0,605 |
| 6 | −1,253 | +0,345 |
| 8 | +0,705 | +2,304 |
| 10 | +1,880 | +3,479 |

O saldo é o orçamento menos o tempo de atravessar a ligação com o limite inferior de bytes, f=1. Um saldo positivo pode pagar trabalho adicional que tenha de ser serial com esse transporte. A 6 tok/s e 4,5 GB/s, pelo menos **5 637 872 027 B** do limite inferior teriam de ser eliminados ou transferidos fora do prazo do prefill. Os 4,5 GB/s são uma hipótese nominal do dispositivo e os 8 GB/s são uma concessão otimista ao enlace, sem overhead. O replay físico isolado de 1058 experts de **outra** trajetória transferiu 13 985 913 600 B úteis em 5,545286 s (RP) e 5,321045 s (PR), respetivamente 2,522 e 2,628 GB/s. Esses preços dizem respeito a payload e drenagem dos grupos desse replay. Este cálculo não os aplicou aos bytes contabilizados pelo cgroup. [Recibo do replay por ordem](../../../../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/prefill_frontier/transport/joint/receipt.json)

### Predicado de decisão

Para uma taxa r e um ganho x sustentados no mesmo trabalho, seja N o ganho necessário acima. Se r < 6, a alteração de prefill sozinha deixa o débito aquém do contrato. Se um **teto** demonstrado U de tempo líquido recuperável ao alterar apenas READ/SET for inferior a N, essa família de alterações é insuficiente nesse cenário. Por exemplo, a 6 tok/s com crédito total basta demonstrar que mais de **2,400018 s** do prefill têm de permanecer no caminho crítico mesmo com as entregas elegíveis gratuitas. Para admitir um teste controlado exige-se r ≥ 6, U ≥ N e uma agenda causal específica com ganho líquido demonstrável ≥ N nos preços declarados, incluindo custos induzidos. Se só houver um teto alto, falta a agenda. Se faltar U, como sucede com este P, o resultado é **indeterminado**. Uma nova política que altera as faltas de decode exige também um preço próprio para r e x. [Critério anterior ao cálculo](protocol.md)

### Reprodução

O protocolo secundário foi fixado em `8683f31f` depois da aquisição da parte 88. O programa autentica os dois recibos do mesmo P (incluindo braço, trace, proveniência e identidade das saídas) e o recibo separado do replay de 1058. A repetição usa apenas estes três compactos. SHA-256 do resultado `c28ba8638b27c6b8ff41c6d6bdf94309053cbf939dbbc350127c13f2c0ee55d9`. [Fontes, digests e resultado completo](receipt.json)

```sh
D=research/qualification-retake/igpu_resident_rank/request_budget/device/packed_prefill
python3 -IB "$D/test_screen.py"
python3 -IB "$D/screen.py" --new-output-dir "$NEW_RESULT"
cmp "$NEW_RESULT/receipt.json" "$D/receipt.json"
```
