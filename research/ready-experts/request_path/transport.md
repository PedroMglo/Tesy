# Quanto custam os bytes que uma cache CPU ainda obriga a ler?

**MEDIDO no NVMe interno.** O portátil precisou de **7,850–8,004 s** para ler os mesmos 1 519 registos, cerca de **20,084 GB** por braço. A antecipação por fase pouco alterou o custo de ler os bytes. A grandeza que pode mudar o pedido é quanto desse serviço ocorre durante trabalho útil. Mantendo a revelação de cada falta no callback, mesmo oferecendo cópias, acertos, restantes leituras e wakes gratuitos, os primeiros finais projetados variam entre **13,697 e 15,065 s**. NO_GO para resolver os 10 s com esta via síncrona. [Protocolo](transport-protocol.md) · [Preços por braço](evidence-transport-20261128-r01/decision.json)

| Ordem e informação disponível | Serviço dos bytes, s | Primeiro final P97 / P106, s | Decode P97 / P106, tok/s |
|---|---:|---:|---:|
| 1. Por callback | 7,890 | 13,697 / 14,950 | 6,875 / 6,591 |
| 2. Toda a fase, sobreposição perfeita | 7,850 | 8,104 / 9,066 | 10,581 / 10,579 |
| 3. Toda a fase, sobreposição perfeita | 7,881 | 8,109 / 9,071 | 10,584 / 10,584 |
| 4. Por callback | 8,004 | 13,811 / 15,065 | 6,863 / 6,581 |

**TRACE_DERIVED_CONDITIONAL.** Só a coluna de serviço foi cronometrada nesta campanha. Para a informação por fase dar uma conversa dentro dos 10 s seria necessário esconder **3,685 / 3,715 s em P97 e 4,934 / 4,964 s em P106**. A soma serial dá 13,685–14,964 s. O executor recebeu o futuro da fase gratuitamente e descartou os pesos após confirmar os bytes nos quatro buffers. Este resultado admite a fixture sobre a fronteira causal do router da camada. [Protocolo com IDs já disponíveis](layer-release-protocol.md)

A banda mínima, se as transferências só começarem no próprio callback e mantiverem um custo proporcional aos bytes, é **4,855 GB/s em P97 e 7,014 GB/s em P106** para os dois relógios. A ligação do Micron negociou 16 GT/s ×4. O teto antes dos cabeçalhos e da arbitragem, com codificação 128b/130b, é aproximadamente 7,877 GB/s. Os quatro braços do portátil entregaram 2,509–2,559 GB/s de registos alinhados incluindo o join e as sentinelas. A ligação por si só permite o prazo teórico. O caminho medido perde-o. [Recibo de máquina](evidence-transport-20261128-r01/provenance.json) · [PCI-SIG, codificação](https://pcisig.com/sites/default/files/files/PCIe_Specification_Webinar_Rev%206_FINAL_0.pdf)

Os denominadores das quatro fases são 37, 625, 834 e 23 registos. Os 1 268 offsets distintos passaram 3 804 SHA-256 antes de timing. As quatro repetições confirmaram 54 684 sentinelas. Incluindo paridade foram pedidos 97 101 545 472 B em O_DIRECT. O contador global do NVMe avançou 189 651 456 setores de 512 B. Inclui qualquer atividade concorrente do disco. O filho durou 44,185 s, com pico do scope 112 689 152 B, zero swap no scope, máximos 57,375 °C CPU, 45,18 °C RTX e 49,85 °C NVMe. A GPU forneceu telemetria. O ensaio abriu o pack dos pesos originais e fez zero forwards. Energia integral desconhecida.

```sh
p=research/ready-experts/request_path
python3 -IB "$p/transport_grade.py" --check "$p/evidence-transport-20261128-r01"
```
