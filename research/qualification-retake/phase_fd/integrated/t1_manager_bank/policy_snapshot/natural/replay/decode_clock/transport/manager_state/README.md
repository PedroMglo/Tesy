# Estado do manager ao entrar no decode

**REPRODUZIDO.** O mesmo turno natural do portátil permite reconstruir os 6 624 destinos de rank que a fixture de entregas ao primário tem de consumir. Ao entrar no decode, R0 e a política prioritária diferem em 455 dos 1 440 pares expert/geração nos respetivos slots. Em 1 255 das 1 656 callbacks, pelo menos um dos quatro destinos (slot ou geração) difere. Um banco de testes que reproduzisse apenas os misses perderia essa diferença nos hits. [Recibo](receipt.json) · [Protocolo](protocol.md)

Os dois estados contêm os vínculos por camada/slot, o estado READY ou vazio, o claim, a geração, a idade, as frequências e os contadores de remap e de decaimento. O R0 reproduziu a fila vazia e os vínculos deduzidos do journal físico. O candidato foi reconstruído a partir do mesmo estado observado no início do prefill, conservando as chamadas 5 e 148, e do banco selado em T1. O verificador reimportou ambos os estados, reproduziu as 1 091 reservas de R0, as 797 de disco e 399 de banco do candidato e os dois digests publicados de slots em todas as 2 987 callbacks. Cada linha do plano inclui os quatro destinos, a vítima, as gerações e a fonte de cada reserva. O índice C290 autenticou as posições e três hashes dos pesos das 1 684 chaves distintas necessárias à união dos dois estados iniciais e do banco. Estas chaves incluem duplicados entre estados apenas uma vez. A ordem original de expulsão em T1 é recuperável no selo de T1. Durante o T2 aqui reconstruído, o conjunto de 353 cópias é fixo.

A preparação lê metadados e traces em CPU. A reprodução dos bytes e o custo da restituição do estado pertencem à fixture física. O controlo e a intervenção já podem ser alimentados pelos mesmos ranks e comparados com as 3 588 entregas esperadas ao primário. [Protocolo dos SET reais e ablação](../service/primary-protocol.md)

Protocolo `4b75b1bb`. Programa selado em `b9524fb5`. Duas execuções em checkout limpa duraram 1,13 e 1,16 s, com RSS máxima de 122 736 KiB. O plano privado de 785 521 B tem SHA-256 `4436b9e8d3ac700a0af1ade3847cc26258639d96788f4a2d926411d1d3176609` e os dois recibos SHA-256 `0ba46bfd0b40f0d3b862c6ac273eabc852b75c58dcfdef2692349e9b4e136b2a`. A parte 68 conserva também a fronteira de prefill em seis ficheiros com 1 588 828 B sob o manifesto `b1dde95daa75b520e8c92f6d0dd6003f5b14a5137b830db7d04656c40c983001`. Os casos negativos exercitam geração, slot, ordem da reserva, fonte e claim pendente.

```sh
u=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/replay/decode_clock/transport/manager_state
timeout 120 prlimit --as=805306368 --cpu=118:120 --fsize=8388608 \
  python3 -IB "$u/seal.py" \
  --family "$PART63/tesy-policy-natural-physical-20261125-r02" \
  --plan "$PART65/tesy-decode-transport-prepare-20261125-r01/plan.json" \
  --index "$C7_RESULTS/c290-integral-lossless-store-20261006/raw/integral-index.json" \
  --new-output-dir "$NEW"
```
