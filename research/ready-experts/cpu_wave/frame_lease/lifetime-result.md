# Chega alguma escrita antes de a CPU acabar de ler?

**TRACE_DERIVED.** A agenda CPU observada nos dois PFJ admite a entrega por ID sem esperar por um consumidor anterior dentro do segundo turno. Das 1 125 escritas num frame, 684 sucederam a uma utilização observada da geração física anterior. Em todas, até a reserva sob mutex chegou depois da operação que delimita superiormente o fim do leitor. Nas 441 restantes, a conversa observada nunca consumiu essa geração física. Os resultados valem para os relógios e a ordem dos dois registos. Antecipar as reservas ou sobrepor duas tiles CPU exige verificar outra vez a vida dos frames. [Protocolo](lifetime-protocol.md) · [Resultados, controlos de falha e testemunhos por wave](evidence-lifetime-20261128-r01/decision.json)

| Mesmo trabalho nominal em cada journal | Prefill 5 | Prefill 148 | Decode até ao primeiro final | Cauda |
|---|---:|---:|---:|---:|
| Waves CPU com pelo menos um expert a consumir | 25 | 186 | 1 100 | 50 |
| Escritas físicas propostas nos frames, faltas CPU | 26 | 548 | 539 | 12 |
| Escritas com um leitor anterior observado, todas seguras | 0 | 188 | 484 | 12 |
| Sem leitor anterior observado desta época física | 26 | 360 | 55 | 0 |
| Promoções CPU usadas pela primeira vez | 14 | 220 | 234 | 1 |
| Waves que consomem pelo menos duas dessas promoções | 2 | 57 | 31 | 0 |
| Promoções nessas waves | 5 | 173 | 70 | 0 |

O instante final de down pode estar em qualquer ponto entre a emissão dos IDs e o próximo remap CPU. As waves da mesma camada dependem do acumulador da anterior. Entre camadas, o router depende do resultado residual. A CPU guarda a ordem das tiles neste replay. Alargámos a última janela até ao fim do journal. O intervalo que usamos inclui todas as leituras dos pesos, mesmo sem um evento próprio de libertação. A comparação usa a última utilização de cada **época física** ao longo de todas as suas promoções, incluindo outras chaves lógicas. A reserva, o início do pread e o primeiro SET foram reconciliados separadamente com as 2 354 gerações de cada journal. Uma leitura anterior à entrada em T2 fica fora da janela observada. O snapshot inicial autenticado tem os 1 000 lugares primários CPU prontos. [Fonte da projeção](lifetime.py) · [Permutação das 1 594 reservas CPU](../../verifier_wait/forecast/retention/eviction/late_owner/contention/sampling/frames-result.md)

| Menor distância do limite superior do leitor à escrita | P97 | P106 |
|---|---:|---:|
| Reserva sob mutex | 12,022 µs | 9,157 µs |
| Início do pread no pack | 0,732 ms | 7,069 ms |
| Início do primeiro SET | 26,450 ms | 34,979 ms |

O mínimo dos dois relógios ocorre na mesma transição, frame físico 1 073, reserva de índice 900 a contar de zero. Ao antecipar deliberadamente outra reserva sobre o frame 1 232, o verificador distinguiu substituição incompatível, ambígua e segura nas três posições do mesmo teste. A contabilidade dá zero espera adicional **por estes leitores** na agenda observada. A margem de 97,448 ms para todos os custos no cenário favorável de P106 continua condicional. Cópias, custos de gestão, possíveis mudanças de despacho e tempo do cliente têm os seus próprios relógios.

**GO para testar promoções em grupo no executor existente.** Antes do primeiro final, 248 de 468 promoções (53,0%) têm outra promoção na mesma wave de primeiro uso. Todos os 469 hits CPU da conversa chegam a um consumidor. No prefill, a quinta tile de CPU0 contém grupos de oito e nove. No decode, a chamada nativa 11 usa quatro novas promoções de CPU0 para os quatro ranks do mesmo token. Estes sites dão dois controlos concretos para a próxima fixture. Os dois journals correspondem a execuções do mesmo trabalho nominal. Qualificar a variante exige preservar as rotas, o trabalho e o estado de entrada no decode e medir a conversa, incluindo código e os restantes critérios M3/M4. O melhor primeiro final nominal medido mantém-se em 17,689 s e o decode correspondente em 5,357 tok/s.

O replay demorou 4,73 s, com pico de RSS de 173 864 KiB. Não abriu pesos nem correu GPU, modelo ou HTTP. Os originais estão nas partes privadas 97 e 106. A projeção reproduzível com os identificadores de geração ocupa 104 242 B comprimidos. [Proveniência, hashes, comandos e orçamento](evidence-lifetime-20261128-r01/provenance.json)

```sh
D=research/ready-experts/cpu_wave/frame_lease
python3 -IB "$D/lifetime.py" --check "$D/evidence-lifetime-20261128-r01"
# No portátil, com as duas partes originais
python3 -IB "$D/lifetime.py" --raw-archive "$TESY_QUALIFICATION_ARCHIVE" --check "$D/evidence-lifetime-20261128-r01"
```
