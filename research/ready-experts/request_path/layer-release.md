# Vale a pena iniciar cada expert logo que a camada revela as rotas?

**NO_GO para financiar um backend novo só com a rota da camada e este caminho de transporte.** A tabela de 1 519 leituras e os 833 grupos ficaram byte a byte iguais quando demos ao executor todos os IDs do tile na primeira remap de cada camada. A política original já reservava essas faltas nesse ponto. O que uma nova fronteira pode alterar é quanto cálculo pode prosseguir enquanto os pesos chegam. Mesmo concedendo até à entrada do router seguinte para receber o último byte, as quatro projeções falharam os 10 s para o primeiro conteúdo final. [Protocolo](layer-release-protocol.md) · [Agenda, preços e relógios](evidence-layer-20261128-r01/decision.json)

| Braço físico | Serviço NVMe, s | P97 primeiro final, s | P106 primeiro final, s | P97 / P106 decode, tok/s |
|---|---:|---:|---:|---:|
| 1. IDs da camada, prazo no router seguinte | 7,893 | 10,851 | 11,941 | 7,893 / 7,639 |
| 2. Oráculo da fase, sobreposição perfeita | 7,804 | 8,072 | 9,034 | 10,689 / 10,683 |
| 3. Oráculo da fase, sobreposição perfeita | 7,792 | 8,080 | 9,042 | 10,662 / 10,654 |
| 4. IDs da camada, prazo no router seguinte | 7,995 | 10,990 | 12,085 | 7,905 / 7,649 |

A coluna de serviço é MEDIDA em quatro workers no portátil. Os relógios do cliente e o decode são TRACE_DERIVED_CONDITIONAL. O piso com prazo na última barreira da camada foi 12,134/13,295 s no primeiro braço e 12,263/13,423 s no quarto, P97/P106. Permitir que os pesos cheguem até ao router seguinte dá crédito inclusive pela atenção seguinte e pela redução que precisa dos próprios pesos. Conservámos o custo do host fora das esperas e o âmbito das chamadas. No quarto braço P106 ainda tem **4,895 s de serviço exposto** até ao primeiro final, dos quais **3,467 s** nos 44 passos anteriores à amostra 45. Para tocar nos 10 s é necessário retirar mais **2,085 s** da soma de tempos expostos ou do restante percurso do pedido. Acelerar só o decode até 6 tok/s seria insuficiente aqui.

Os 7 012 top-4 em 1 867 visitas a camada coincidiram com o digest do target nas duas observações. O início da remap antecipou gratuitamente o último registo de ranks em até 55,344/63,901 µs. Confirmámos novamente 3 804 hashes completos, 54 684 sentinelas e 97 101 545 472 B pedidos, com o mesmo binário e os mesmos parâmetros do ensaio por callback. O filho durou 43,776 s, pico do scope 113 852 416 B, zero swap no scope, máximos 57,50 °C CPU, 45,61 °C GPU e 49,85 °C NVMe. O hardware mediu transporte dos pesos do 120B. A RTX forneceu telemetria e houve zero forwards. [Proveniência e identidade das duas tabelas](evidence-layer-20261128-r01/provenance.json)

```sh
p=research/ready-experts/request_path
python3 -IB "$p/layer_release.py" grade --check "$p/evidence-layer-20261128-r01"
```
