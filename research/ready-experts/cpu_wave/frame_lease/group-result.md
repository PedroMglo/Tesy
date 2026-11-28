# Quando é que adiantar vários experts faz a CPU esperar menos?

A medição física posterior qualificou a entrega do grupo de quatro no decode. Os seis misses no prefill limitaram o efeito incremental dos outros oito hits. [Medições por registo e regime](group_service/README.md)

**GO para testar o serviço em grupo no backend existente.** Só duas das 90 waves com várias promoções ganharam, nos dois registos, tempo adicional ao retirar as cópias de mais de um expert. Uma ocorre na camada 12 do prefill de cinco posições, com dois hits. A outra ocorre na CPU0 do decode, com quatro. Se o hit também dispensar a leitura do NVMe, essa condição verifica-se em 35 waves comuns aos dois registos. O resultado é condicional aos instantes observados de entrada na barreira e de publicação pelos outros produtores. O tempo ganho pelo cliente continua desconhecido. [Critério prospetivo](group-protocol.md) · [Custos dos três cenários e coordenadas dos casos](evidence-groups-20261128-r01/decision.json)

| Cenário antes do primeiro final, soma em ms nas mesmas 90 barreiras | Todos os hits P97 | Melhor hit de cada wave P97 | Todos P106 | Melhor de cada wave P106 |
|---|---:|---:|---:|---:|
| Retirar as três durações SET | 38,591 | 35,465 | 39,239 | 34,032 |
| Retirar as durações do READ e dos três SET | 510,277 | 148,766 | 495,034 | 111,114 |
| Entregar os hits até à entrada da barreira | 552,572 | 148,766 | 523,962 | 111,114 |

O melhor hit em cada wave é uma escolha retrospetiva. Para um máximo entre publicações concorrentes, adiantar individualmente um produtor só liberta o consumidor até à chegada do segundo mais tardio. É por isso que, nesta conta local, a soma dos ganhos isolados coincide com o melhor hit e as intervenções simultâneas podem superar essa soma. Retirando só SET, o excedente dos grupos foi 3,126 ms em P97 e 5,207 ms em P106. Retirando também READ foi 361,511 e 383,920 ms. O segundo cenário concede o serviço original das leituras evitadas. A retenção, a disponibilidade efetiva do banco, a coordenação e o efeito sobre os outros workers têm de ser pagos numa execução do candidato.

| Fase | Waves em grupo | Crédito só de SET para o grupo P97 / P106, ms | Excedente sobre otimizar um único hit P97 / P106, ms |
|---|---:|---:|---:|
| Prefill 5 | 2 | 1,618 / 1,406 | 0,711 / 0,179 |
| Prefill 148 | 57 | 19,850 / 18,741 | 0,165 / 1,012 |
| Decode até ao primeiro final | 31 | 17,123 / 19,092 | 2,250 / 4,016 |
| Cauda | 0 | 0 / 0 | 0 / 0 |

Na quinta tile de CPU0 do prefill, para o grupo de nove, os restantes oito hits acrescentaram zero ao efeito de retirar os SET do melhor hit, em ambos os registos. Já na chamada 11 do decode, a CPU0 precisa dos quatro experts. Retirar os SET dos quatro liberta localmente 0,912 ms em P97 e 1,748 ms em P106. Só o melhor hit dá 0,400 e 0,259 ms. Este regime de decode é o teste físico mais direto. O prefill de nove é um controlo da explicação que atribuiria o ganho simplesmente à cardinalidade.

Sem mudar a chegada dos outros produtores, 34 das 90 waves em P97 e 37 em P106 dão zero mesmo com os hits prontos à entrada. Contámos os 220 primeiros usos isolados até ao primeiro final e o único hit isolado da cauda separadamente. A verificação reconcilia todos os últimos produtores registados nas barreiras com promoções, conserva as esperas pelo wakeup e publica todos os pares por wave. Os controlos obrigam o avaliador a distinguir empate entre produtores, um não-hit mais lento e dados que já estavam presentes. O replay decorreu em 3,54 s com 128 724 KiB de RSS. Sem pesos, GPU, forwards ou HTTP. O melhor resultado medido para a conversa permanece em 17,689 s até ao primeiro final e 5,357 tok/s. [Dados por wave](evidence-groups-20261128-r01/barriers.json.gz) · [Comando, hashes e recursos](evidence-groups-20261128-r01/provenance.json)

```sh
D=research/ready-experts/cpu_wave/frame_lease
python3 -IB "$D/groups.py" --check "$D/evidence-groups-20261128-r01"
```
