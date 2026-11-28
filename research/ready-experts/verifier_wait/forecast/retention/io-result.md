# Vale a pena prototipar outro serviço de experts?

**GO para testar a entrega ao consumidor, NO_GO para financiar já uma reescrita integral.** No NVMe interno do portátil, a entrega só dos pesos que precisavam de entrar no prefill custou 3,211–3,235 s. O orçamento deste prefill no braço nominal mais exigente é 3,484 s. Existe margem física de **249–272 ms** para trabalho adicional que ficar exposto nesse braço. O primeiro final projetado do pedido inteiro continua em **9,926–10,230 s**. P106 falha até no extremo mais favorável, por 5,223 ms. O mecanismo de produto permanece **INCONCLUSIVE** e precisa de mudar também o tempo exposto no consumidor. R0 `slots40-persistent` mantém-se como controlo, M3 PARTIAL e M4 NOT_MET. [Pré-registo](io-protocol.md) · [Resultados nos oito braços por repetição](evidence-io-20261128-r01/grade.json)

| Medição no portátil | Leituras na chamada de 5 + na de 148 | Volume alinhado | Tempo das leituras 5 + 148 | Total no leitor | Folga de I/O no braço mais exigente |
|---|---:|---:|---:|---:|---:|
| D1, banco de referência | 34 + 858 | 11,794 GB | 0,162 + 3,710 s | 3,871 s | −388 ms |
| E2, só as primeiras aquisições obrigatórias | 34 + 692 | 9,599 GB | 0,181 + 3,030 s | 3,211 s | +272 ms |
| E3, mesmas aquisições | 34 + 692 | 9,599 GB | 0,173 + 3,062 s | 3,235 s | +249 ms |
| D4, banco de referência | 34 + 858 | 11,794 GB | 0,179 + 3,717 s | 3,896 s | −412 ms |

**MEDIDO.** A redução do tempo de leitura foi 659,947 ms no primeiro par e 660,692 ms no segundo. Ambos usam o mesmo pack do GPT-OSS-120B MXFP4 original, quatro buffers no mesmo leitor `io_uring`, O_DIRECT, os dois retornos externos e offsets por ordem crescente dentro de cada retorno. E recebe antecipadamente a lista correta de pesos de todas as cinco tiles da segunda chamada. A fila é física e a seleção possui informação futura. A verificação prévia comparou os três SHA-256 de 848 registos, e cada um dos 3 236 registos cronometrados passou nove amostras de oito bytes. O tempo de cada grupo acaba na última conclusão. [Recibo físico](evidence-io-20261128-r01/observed.json) · [Verificador e construção do plano](prefill_io.py)

**TRACE_DERIVED.** As 892 leituras de referência repartem-se em 726 primeiras faltas ausentes de ambas as fontes, 125 experts presentes à entrada e já perdidos quando pedidos, 38 adquiridos antes dentro da chamada e três nas duas classes de disponibilidade. As 125 chaves exclusivas da entrada representam 1 652 400 000 B de payload distinto. Quarenta e nove vieram do primário da frente e 25 do primário de trás. Os bancos secundários conservavam inicialmente 39 e 12, respetivamente. Este volume descreve as origens que o espelho teria de proteger ao longo da chamada. A ocupação simultânea de uma agenda finita é outra grandeza. [Snapshots, contagens e quotas](evidence-entry-20261128-r01/receipt.json) · [Limite do reuso dentro da chamada](README.md)

Em P97, o espelho ideal daria 9,926–10,151 s até ao primeiro conteúdo, e em P106 daria 10,005–10,230 s. O cálculo combina a duração de prefill anteriormente simulada com o tempo físico pelo máximo, concedendo toda a sobreposição possível, e mantém o decode por ID confirmado no mesmo braço. Por isso os 660 ms medidos no leitor só contam na medida em que adiantem a última dependência do cliente. A previsão conjunta mais agressiva no decode gerou 1 874 leituras sem consumidor e ocupou mais de 11,7 s de I/O antes da primeira peça. [Decode e ablação com o mesmo transporte](../io/README.md)

**Próxima experiência admitida.** Num fragmento de prefill com experts residentes à entrada e procurados após uma expulsão, conservar antes da expulsão os bytes exatos e registar a camada que os consome. Em paralelo, tratar as leituras obrigatórias que o routing já tornou disponíveis. Comparar o candidato com a mesma memória e agenda de captura com reuso desligado e com R0 independente. Medir o intervalo submissão → bytes prontos → três SET → consumidor, sob um orçamento finito de slots e com as duas fronteiras de retorno. Comparar KV, máscaras, rotas, logits completos e primeiro decode antes de cronometrar uma conversa. A campanha física da tabela fez zero forwards e nenhuma inferência na RTX. A melhor conversa inteira medida continua a ser **17,689 s / 5,357 tok/s**. Código, sessão sustentada e qualificação de produto desta combinação estão NOT_RUN. [Qualificação natural anterior](../../../cpu_wave/README.md)

**Recursos.** C55 observou o portátil durante 60,967 s antes da medição. O leitor demorou 22,513 s, incluindo 8,251 s de paridade. Pediu 53 998 190 592 B ao pack e o dispositivo completo registou 53 999 767 552 B de leituras. Pico de 119 394 304 B no scope, zero swap, CPU 56,25 °C, GPU 44,01 °C e NVMe 47,85 °C. A energia amostrada da GPU em repouso foi de cerca de 69 J. A energia do sistema é desconhecida. O arquivo privado tem 27 ficheiros e 619 039 B. [Comandos e hashes](evidence-io-20261128-r01/provenance.json) · [Manifesto verificado](evidence-io-20261128-r01/archive.json)

```sh
d=research/ready-experts/verifier_wait/forecast/retention
python3 -IB "$d/replay.py" --check "$d/evidence-20261128-r01/receipt.json"
python3 -IB "$d/entry.py" --check "$d/evidence-entry-20261128-r01/receipt.json"
python3 -IB "$d/prefill_io.py" grade --observed "$d/evidence-io-20261128-r01/observed.json" --check "$d/evidence-io-20261128-r01/grade.json"
```

Os verificadores públicos correm sem pesos, GPU ou originais privados. Uma nova medição física precisa do índice e pack C291 verificados, dos gates C55 e de uma identidade e destinos exclusivos.
