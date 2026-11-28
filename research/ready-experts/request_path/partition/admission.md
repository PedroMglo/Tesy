# Dar uma vaga só aos pesos que vão voltar

**NO_GO para os dois filtros de frequência neste regime.** No segundo turno natural, o melhor dos dois filtros pediu 1 315 leituras CPU perante 1 110 no primário atual com o seu banco. Nos 32 passos do código fornecido precisou de 888, perante 753. O outro filtro chegou a 1 430. O controlador serve integralmente o expert pedido mesmo quando recusa conservá-lo. O custo da recusa aparece na próxima utilização. [Protocolo](admission-protocol.md) · [Recibo por fase e SHA dos estados](evidence-admission-20261128-r01/decision.json)

| Leituras CPU cruas / com reposição dos membros do incumbente | Primário atual + banco | LRU global | Filtro da vítima LRU | Filtro da frequência mínima |
|---|---:|---:|---:|---:|
| Segundo turno natural | 1 110 / 1 110 | 1 415 / 1 577 | 1 518 / 1 837 | 1 315 / 1 523 |
| Nominal153 fornecido | 1 139 / 1 139 | 1 295 / 1 392 | 1 728 / 2 262 | 1 399 / 1 709 |
| Code153 fornecido | 2 228 / 2 228 | 2 139 / 2 250 | 2 808 / 3 343 | 2 302 / 2 636 |

A LRU global poupa 89 leituras no último caso antes da reposição. Restituir 111 membros do controlo converte isso em mais 22 leituras. No prefixo natural os filtros LRU e mínimo pediram 3 978 e 3 791 leituras, perante 3 317 no primário e banco contínuos. A fonte fornecida autentica os 1 000 membros do primário CPU em P. Conservámos essa entrada com o banco vazio nos dois repeats C294 de cada caso. Os dois repetem exatamente a sequência lógica relevante para o controlo de contagens e o conjunto final. Cada leitura representa um pedido de 13 221 888 B ao pack. Nada neste ensaio moveu esses bytes fisicamente.

**Onde houve ganho parcial.** O filtro LRU precisou de 501 leituras durante a call de 148 contra 532 no controlo. Na call de 5 pediu 75 contra 26 e, do fim do prefill até ao primeiro conteúdo final, 891 contra 540. Nos casos fornecidos as leituras de prefill passaram de 582 para 511 e de 1 475 para 1 378, seguidas de fortes regressões de decode. O próximo teste mantém a entrada e a saída reais do prefill, para verificar a parte que poderia compor-se com o resto do runtime. [Experiência registada](switch-protocol.md)

O verificador isolado executou o commit `0784eb68827336ef85b084ad47c043d7d1d66d29`, árvore `529a6eab97f9ec799883f10d0b1e105e81d35746`. O selo independente demorou 3,91 s, com 157 892 KiB de RSS, e a avaliação demorou 4,90 s, com 185 428 KiB. Cada caso conserva os misses por wave e o conjunto final no certificado comprimido. O replay autentica as quatro capturas C294, os dois PFJ e os dois pares WRT. As datas e os clocks de cada população mantêm-se distintos. O objetivo de produto continua por demonstrar. [Código](admission.py) · [Certificado compacto](evidence-admission-20261128-r01/certificate.json.gz)

```sh
p=research/ready-experts/request_path/partition
python3 -IB "$p/test_admission.py"
python3 -IB "$p/admission.py" --check "$p/evidence-admission-20261128-r01" \
  --plan "$p/plan-admission-20261128-r01/states.json.gz"
python3 -IB "$p/admission.py" --archive "$TESY_ARCHIVE" --seal "$WORK/admission-plan"
python3 -IB "$p/admission.py" --archive "$TESY_ARCHIVE" --c294-raw "$TESY_C294_RAW" \
  --new "$WORK/admission" --plan "$WORK/admission-plan/states.json.gz" \
  --plan-sha256 e321e2956e7c4c6803784e3a72b6d3f565c7063dff221bb6797d66c6e92c02d0
```
