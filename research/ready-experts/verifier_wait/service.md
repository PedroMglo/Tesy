# Um serviço bloqueante cabe no prazo do cliente?

**NO_GO aos preços de READ e SET observados no portátil.** Mesmo concedendo quatro leitores já disponíveis, aquisição gratuita das vítimas e zero custo de coordenação, o melhor primeiro conteúdo fica em **11,433 s**. Com o banco secundário, o decode completo caberia nos 7,833 s de 47 IDs a 6 tok/s. A primeira peça final continua a decidir. O resultado é TRACE_DERIVED e condicional à agenda bloqueante e ao preço de prefill simulado. [Protocolo](service-protocol.md) · [Todos os braços e limites de READ](evidence-service-20261128-r03/service.json)

| Journal de preços e prefill | Banco secundário no decode | Serviço dos pesos até à primeira peça | Primeiro conteúdo composto | Decode composto |
|---|---|---:|---:|---:|
| P97 | Desativado | 6,449 s | 12,482–12,711 s | 8,603–8,659 s |
| P97 | 252 entradas CPU + 101 para a etapa GPU, ambas em RAM | 5,400 s | 11,433–11,662 s | 7,529–7,584 s |
| P106 | Desativado | 6,432 s | 12,557–12,787 s | 8,591–8,646 s |
| P106 | Mesma seleção, renovada | 5,416 s | 11,541–11,770 s | 7,552–7,608 s |

No prefill, ambos os controlos conservam a mesma simulação de duas tiles em pipeline e banco treinado. No decode, o target escolhe os quatro experts. Cada camada aguarda os seus registos em falta e as três cópias de cada registo até ao consumidor. Dentro da camada, o cálculo de custo deixa os quatro leitores começar juntos. O banco promove 299 das 1 067 cargas até à primeira peça e quatro das últimas 24. Aos preços de serviço históricos, a promoção retira **1,016–1,049 s** do intervalo crítico modelado. A combinação foi creditada conjuntamente, sem subtrair duas vezes os mesmos segundos. A cópia dos pesos promovidos entra no preço. A captura das vítimas e qualquer disputa adicional continuam gratuitas nesta concessão.

A 4,5 GB/s decimais, para a receita com banco caber usando o mesmo volume e os mesmos SET, seria necessário reduzir uniformemente as durações de READ entre **30,1%** na combinação mais permissiva e **37,6%** para cobrir também a pior. Elevar só o teto agregado de 4,5 para 8,0 GB/s não muda o primeiro conteúdo ao preço histórico dos jobs. A antiga medição de io_uring deu 4,85% e 5,55% de redução mediana em duas waves de quatro leituras; o sinal nos pedidos isolados variou com a ordem. Uma fila mais rápida pode contribuir para outro mecanismo que já mostre onde obtém os segundos em falta. [Experiência física com io_uring](../renewal/README.md)

As 1 091 reservas no decode dos dois journals têm uma chave dentro da união real dos experts escolhidos em S. As contagens coincidem em cada uma das 46 chamadas. Há 782 camadas com serviço e 874 completamente residentes em 1 656 visitas. Em S, a identidade individual da falta ficou por observar. Este cálculo usa as gerações e os tempos de P97 ou de P106, a duração residente medida em S e os relógios W do cliente. Somar o serviço à duração residente pressupõe que a entrega da camada bloqueie a continuação e não se sobreponha com o trabalho desta. Para testar uma fronteira de backend diferente, a observação mínima é o instante causal de disponibilização do expert em relação ao consumidor, com as cópias e os erros de previsão cobrados até ao primeiro conteúdo.

O primeiro replay procurou uma linha temporal até para as camadas integralmente residentes. O compacto guarda só as camadas com reservas. A correção verificou que as ausentes tinham zero reservas no ledger completo e que S executara 36 remaps em cada passo. A tentativa original de 0,35 s foi preservada. A repetição levou 0,70 s e 35 584 KiB de RSS, com zero GPU e zero modelos. [Falha original](evidence-service-20261128-r03/failure-r01.json) · [Identidades e comandos](evidence-service-20261128-r03/provenance.json)

~~~sh
u=research/ready-experts/verifier_wait
python3 -IB "$u/service.py" --check "$u/evidence-service-20261128-r03/service.json"
p="$TESY_VERIFIER_ARCHIVE/part-01/tesy-verifier-wait-20261128-r01/S/raw"
python3 -IB "$u/service.py" --check "$u/evidence-service-20261128-r03/service.json" --serial-native "$p/tesy-verifier-wait-20261128-r01-s.capture/native.json"
~~~
