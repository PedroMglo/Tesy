# Quantas previsões identificam uma leitura real do pack?

**GO para medir a antecedência, INCONCLUSIVE quanto à vantagem de ordenação no prefill.** No C292 de trabalho fornecido, 319 das 397 propostas de prefill com limite de quatro por destino corresponderam a uma reserva real. Cobriram 319 das 2 103 gerações ausentes elegíveis nas tiles e camadas com sinal. Quando as duas políticas podem efetivamente enviar o mesmo número de propostas em cada decisão, a recência ganha na CPU (35 contra 31) e a projeção ganha na CUDA (3 contra 1). A projeção encontra trabalho adicional sobretudo quando já estão residentes as sugestões que a recência consegue fazer. A disponibilidade do preditor e o tempo ganho ao servir uma dessas chaves continuam por medir. [Protocolo de teto comum](protocol.md) · [Protocolo de emissão igual](equal-issues.md)

O C292 usou o GPT-OSS-120B original, 189 tokens de entrada e 32 tokens de continuação fornecidos. O seu journal começou com 1 440 slots vazios. Das 38 tiles, há ativações C270 autenticadas de três tiles de prefill e quatro posições de decode. Todos os 3 400 quartetos identicamente ordenados se ligam ao respetivo tensor por posição e camada, incluindo a última saída mascarada. No processo C292, **todas as 4 501 reservas** têm um worker identificado, uma leitura do offset correto do pack, três SET ordenados e publicação da mesma geração. O crivo usa apenas a primeira geração elegível distinta de cada chave oferecida na tile, com RANKS e demanda da geração confirmados. [Paridade das árvores C270 e C292](../../igpu_resident_rank/request_budget/device/pack_native/numeric/README.md)

| Fase / dispositivo | Gerações elegíveis nos sítios com +1 | Propostas limitadas a quatro | Gerações identificadas | Na primeira wave | Ofertas sem procura | Gerações identificadas com todas as ofertas / ofertas |
|---|---:|---:|---:|---:|---:|---:|
| Prefill CPU | 1 495 | 278 | 222 | 190 | 56 | 1 260 / 1 668 |
| Prefill CUDA | 608 | 119 | 97 | 89 | 22 | 508 / 622 |
| Decode CPU | 95 | 104 | 69 | 69 | 35 | 69 / 104 |
| Decode CUDA | 52 | 52 | 44 | 44 | 8 | 44 / 52 |

Aumentar a emissão do prefill para a união dos IDs previstos em todas as posições da tile identificaria 1 768 gerações e produziria 522 ofertas sem procura. O teto de quatro identificou 319 e produziu 78 sem procura. Cada leitura efetiva da fixture física usa 13 221 888 B pedidos ao FD e 13 219 200 B de payload. Nenhuma oferta do replay emite leituras. Somar o tempo de serviço das gerações cobertas duplicaria períodos em que os quatro workers trabalham em paralelo.

| Subconjunto com tile anterior concluída | Sítios | Projeção até 4, hits / ofertas | Recência até 4, hits / ofertas | Ofertas iguais por política | Hits projeção / recência |
|---|---:|---:|---:|---:|---:|
| Prefill CPU | 48 | 126 / 182 | 35 / 42 | 42 | 31 / 35 |
| Prefill CUDA | 20 | 55 / 75 | 1 / 5 | 5 | 3 / 1 |
| Decode CPU | 96 | 69 / 104 | 0 / 43 | 19 | 12 / 0 |
| Decode CUDA | 44 | 44 / 52 | 0 / 13 | 7 | 7 / 0 |

Na CPU há 35/48 sítios de prefill sem qualquer emissão emparelhada. Na CUDA há 18/20 nessa situação. O desempate por ID crescente e a ordenação por frequência foram fixados antes de pontuar. A comparação de decode cobre só quatro posições e inclui as primeiras posições depois da tile larga. O comparador usa a última tile que realmente terminou no destino, mesmo quando a sua ativação de origem foi omitida pelo observador C270.

Entre o fim do último remap da fonte e a entrada do primeiro do alvo, as medianas do journal foram 3,743 / 1,467 ms na CPU/CUDA de prefill e 1,741 / 0,946 ms em decode. A 4,5 GB/s úteis, um payload inteiro ocupa 2,938 ms de link antes de SET e a 8 GB/s ocupa 1,652 ms. Estes intervalos pertencem ao C292 com captura síncrona. Determinar o que chega a tempo exige a disponibilidade efetiva da projeção, concorrência dos bytes e prazo de cada wave. O C281 natural usa histórico quente, 5+148 de entrada e 47 saídas; a sua distribuição de faltas e o seu prazo não foram medidos neste cruzamento.

## Reprodução

Protocolo inicial 537456cb e código 9e1ee4d6. Extensão de mesmo volume 960d9347 e código d8c49d90. Duas execuções por método, de 0,70–0,93 s e até 194 868 KiB de RSS (0,94 s na última repetição). Recibos deterministas SHA-256 5e83418c00905348b46a442f0caee4affbf7ab3073a3faaeff8f958971e02c05 e 277b544287500017c7d4201b520dd39f8ae3eb8ab85f4a4900100642d6687aa8. O verificador de emissão igual reabre o journal e regenera o primeiro recibo completo. A parte 114 conserva os quatro resultados juntamente com os dois replays económicos P97/P106. Foram usados apenas CPU, ativações e parâmetros de router previamente verificados. [Recibo de arquivo](../../private_archive/part-114.json) · [Construção do bundle privado](../tf32/README.md)

```sh
export LC_ALL=C PYTHONUTF8=1 PYTHONCOERCECLOCALE=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
timeout 90 prlimit --as=536870912 -- "$TESY_REPO/.venv/bin/python" -IB "$UNIT/score.py" \
  --part23 "$ARCHIVE/part-23" --part95 "$ARCHIVE/part-95" --c7 "$C7" --bundle "$BUNDLE" --new-output-dir "$NEW1"
timeout 90 prlimit --as=536870912 -- "$TESY_REPO/.venv/bin/python" -IB "$UNIT/equal.py" \
  --part23 "$ARCHIVE/part-23" --part95 "$ARCHIVE/part-95" --c7 "$C7" --bundle "$BUNDLE" --original "$NEW1" --new-output-dir "$NEW2"
```
