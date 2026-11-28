# O proprietário de um expert CPU pode mudar sem mover os pesos?

**GO para testar a entrega ao operador GGML.** Em 1 594 reservas do segundo turno, uma troca de identificadores conservou o conteúdo de todos os lugares da referência de cópia, incluindo a entrada no primeiro decode. As 469 promoções e as 1 349 capturas couberam nos mesmos 1 252 frames, em ambas as ordens admissíveis de tiles. Esta é uma prova de conservação com reservas drenadas, derivada do trace. [Protocolo](frames-protocol.md) · [Resultados por fase](evidence-frames-20261128-r01/frames.json)

| Fase | Reservas | Promoções | Capturas de vítimas |
|---|---:|---:|---:|
| Prefill | 808 | 234 | 713 |
| Decode anterior ao primeiro final | 773 | 234 | 628 |
| Cauda | 13 | 1 | 8 |

A soma dos payloads da referência que a troca pode dispensar é 6 199 804 800 B nas promoções e 17 832 700 800 B nas capturas. Continuam a pagar-se 14 871 600 000 B nas 1 125 faltas. A arena CPU tem 1 000 frames primários e 252 secundários, 16 553 803 776 B endereçáveis e 3 365 376 B de padding. Cada frame identifica três componentes distintos. Em cada reserva, uma referência independente que copia as identidades e o controlador que troca frames concordam em todas as chaves, gerações e componentes.

O teste também comparou, em cada journal original, 775 reservas de captura, 178 de promoção e 584 sobrescritas identificáveis com a publicação do respetivo produtor. Houve zero inversões. A menor folga na captura foi 6,931 ms em P97 e 9,008 ms em P106. O journal omite a libertação pelo último consumidor. A segurança com kernels em voo e com tiles sobrepostas permanece desconhecida. Os bytes são lógicos e o teste não lhes atribui segundos. O máximo disponível para custos adicionais no cenário creditado de P106 é 97,448 ms. O piso integral é 10,549 s. [Comparação das entregas CPU e CUDA](tiers-result.md)

A execução demorou 3,45 s e atingiu 124 656 KiB de RSS. Zero forwards e pedidos HTTP. M3 PARTIAL e M4 NOT_MET. [Comando, custos e proveniência](evidence-frames-20261128-r01/provenance.json) · [Arquivo selado](evidence-frames-20261128-r01/archive.json)

```sh
S=research/ready-experts/verifier_wait/forecast/retention/eviction/late_owner/contention/sampling
python3 -IB "$S/frames.py" --check "$S/evidence-frames-20261128-r01/frames.json"
python3 -IB "$S/test_frames.py"
```
