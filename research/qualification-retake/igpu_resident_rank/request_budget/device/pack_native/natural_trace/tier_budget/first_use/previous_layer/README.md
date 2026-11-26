# Um router de antecedência deixa 71,395 ms por recuperar

**NO_GO para atingir 10 s no P apenas antecipando as primeiras leituras CPU ao fim da camada anterior.** Mesmo acertando gratuitamente todos os experts e podendo começar a ler qualquer fração dos seus pesos a 8 GB/s úteis, restam **162,036 ms** nas callbacks. O pedido admite **90,641 ms** de trabalho CPU nesse cenário. O piso até ao primeiro conteúdo final é, portanto, **10,071395 s**. A 4,5 GB/s o piso é **10,411062 s**. A falha do primeiro final basta para excluir os alvos conjuntos sob estas premissas. [Recibo](receipt.json) · [Definição do orçamento e do relógio](../../README.md)

| Modelo de serviço | Trabalho que pode sair das callbacks | Piso residual nas callbacks | Margem até 10 s |
|---|---:|---:|---:|
| 8 GB/s, admite expert parcial | 3 660 912 360 B (73,85%) | 162,036 ms | −71,395 ms |
| 8 GB/s, só experts inteiros antecipados | 256 de 375 | 196,636 ms | −105,994 ms |
| 4,5 GB/s, admite expert parcial | 2 699 535 794 B (54,46%) | 501,703 ms | −411,062 ms |
| 4,5 GB/s, só experts inteiros antecipados | 177 de 375 | 581,645 ms | −491,003 ms |
| Quatro workers, READ aos preços da própria execução | 721,901 ms do piso original | 1 314,894 ms | −1 224,253 ms |
| Quatro workers, metade de cada preço de READ | 625,950 ms do piso original a metade do preço | 392,448 ms | −301,807 ms |

A margem é **orçamento menos piso residual**. O JSON guarda ns inteiros e a tabela usa ms. Os bytes são truncados até ao último byte completo por grupo. Para o piso temporal fracionável o cálculo concede também a eventual fração de byte à fronteira do intervalo. O modelo de quatro leitores substitui o preço de banda e conserva, por grupo, o maior de dois limites do serviço READ: o maior job e o worker-tempo dividido por quatro. Todos os SET, trabalho do preditor, staging e retenção são gratuitos.

| Prefill observado | Jobs CPU estritos | Intervalos elegíveis | Tempo nesses intervalos | Jobs em camada 0 | Piso residual parcial, 8 GB/s | Piso residual parcial, 4,5 GB/s |
|---|---:|---:|---:|---:|---:|---:|
| Chamada de 5 | 40 | 20 | 111,300 ms | 1 | 2,831 ms | 31,074 ms |
| Chamada de 148, cinco tiles | 335 | 86 | 657,079 ms | 13 | 159,205 ms | 470,630 ms |

As 110 callbacks servem 375 primeiras procuras CPU distintas, 4 957 200 000 B úteis. Todos vencem na primeira wave ou na única wave da respetiva camada. Para 106 grupos, a última callback da camada imediatamente anterior e a primeira da atual são consecutivas no journal da mesma tile. O intervalo começa e termina sem LOADING, claims nem fila. Nenhum serviço READ/SET ou evento de reserva, despacho ou publicação atravessa o intervalo. Os outros quatro grupos estão na camada 0 e somam 14 experts. Conservam horizonte zero. Cada horizonte pertence a uma só camada e os 110 são disjuntos. A tabela por callback identifica chamada, tile, camada, wave, intervalo e dois preços de cada grupo. [Dados por camada e tile](windows.tsv)

Os 768,379 ms somados entre camadas excedem o preço bruto de 619,650 ms para todos os bytes a 8 GB/s. A camada que tem tempo de sobra não o pode ceder àquela cujos experts só serão preditos mais tarde. No caso mais favorável ainda é preciso que **571 156 928 B** atravessem a interface mais cedo ou deixem de a atravessar nestes sítios, ou que se ganhem 71,395 ms fora deles. Também reabre a conclusão um desenho que consiga serviço dentro da callback anterior, entre tiles/chamadas ou com previsão utilizável mais cedo. Nessa hipótese haverá que cobrar acertos, desperdício, concorrência e tempo de serviço no mesmo pedido. O journal identifica o intervalo do host; a disponibilidade dos futuros ranks nesse ponto foi concedida ao preditor.

O antecedente da parte 37 dava a 875 primeiras gerações de ambos os tiers até à última wave e creditava também intervalos entre tiles e calls. A conclusão presente usa a conversa P com o pack no NVMe interno, as suas próprias 375 primeiras cargas CPU, 7 012 quartetos autenticados, 47 saídas confirmadas e o validador original. Os tempos do antecedente não entram no cálculo. [Estudo anterior](../../../../../../../../phase_fd/integrated/router_release/README.md) · [População e hipóteses de primeira utilização](../README.md)

**Reprodução sem modelo.** Protocolo congelado em `4af07177`. R01 sobre os originais e R02 sobre a cópia arquivada da parte 97 produziram o mesmo recibo SHA-256 `db207a310396e24e86b28766292cffe12b20f3f8ac2cfc637839a7b28da9d600` e a mesma tabela `084c73715faacc37af23d2a759dbe6453b5b5746014ae8f70fdc2ddf83543ea0`. Cada processo levou 0,46 s com 68 120 e 68 152 KiB de RSS. Os três testes cobrem janelas entre camadas, fila ou leitura em voo, camada 0, ordenação, transferências parciais e os quatro leitores. [Protocolo](protocol.md) · [Verificador](score.py)

```sh
python3 -IB -m unittest discover -s "$STUDY"
timeout 60 prlimit --as=536870912 -- python3 -IB "$STUDY/score.py" \
  --family "$FAMILY_P" --backend "$C291_SOURCE" --new-output-dir "$NEW"
```
