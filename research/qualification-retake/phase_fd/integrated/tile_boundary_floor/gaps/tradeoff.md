# Combinar ganhos no prefill e no decode do mesmo pedido

**Uma melhoria no decode pode compensar trabalho que sobra no prefill.** Na parte 40, concedemos ao prefill os 40 slots, as 353 vítimas em RAM e a escolha futura perfeita. A 4,5 GB/s, as suas 793 leituras mínimas custam 2,330 s de payload útil. Os 205 intervalos de R0 entre camadas somam 1,143 s. Se esses preços se mantiverem, o cruzamento nominal exige **6,977 tok/s** de decode na convenção de 47 saídas. Mantendo o decode a 6,000 tok/s, a mesma hipótese exigiria **8,502 GB/s** de prefill.

| Banco à entrada de T2 | Leituras mínimas | Decode necessário se o prefill conservar os dois preços | Fator comum no decode e nos intervalos com banda fixa | Fator comum no decode, intervalos e banda |
|---|---:|---:|---:|---:|
| Vazio | 944 | 7,468 tok/s | 1,2071× | 1,1509× |
| 353 publicações | 870 | 7,219 tok/s | 1,1728× | 1,1296× |
| 353 vítimas | 793 | 6,977 tok/s | 1,1392× | 1,1074× |

Por exemplo, o último cruzamento corresponde simultaneamente a 6,644 tok/s de decode, 4,983 GB/s úteis no prefill e 1,032 s de intervalos entre camadas. O fator de 1,1074× parte de um decode **já a 6 tok/s**. A referência natural OFF medida foi 4,752 tok/s. A decisão no produto ainda exige comprar o banco durante T1, servir as cópias, manter o grafo exato e validar o histórico e a resposta no endpoint. A convenção alternativa de 46 avaliações dá 6,828 tok/s no primeiro cenário do banco de vítimas. [Resultados em ambas as convenções](tradeoff-receipt.json) · [Medição do controlo natural](../../README.md)

Para cada braço, seja S = 10 − primeiro final + prefill + decode, obtido do pedido observado, V o seu payload mínimo, b a banda útil, G os intervalos drenados e D o número de saídas ou avaliações. O cruzamento satisfaz V/b + G + D/v = S. Cobram-se as leituras do prefill uma vez. A taxa v é a do decode integral e já inclui a entrega de pesos dessa fase. A relação mantém o termo do cliente que inclui a cauda posterior ao primeiro conteúdo final. Essa cauda pode mudar numa intervenção. Os cruzamentos ignoram todo o trabalho adicional e concedem um oráculo à cache. Um candidato em condições reais tem de ser medido. [Âmbito e pré-registo](tradeoff-protocol.md)

Freeze de código f8e11449. Duas reproduções em 0,02 s, até 18 916 KiB de RSS, deram SHA-256 94cdca0ef2c2ccc9ee100b265dc87f96c48dcb46e3d2a976cb5c9b37309d99a7.

```sh
u=research/qualification-retake/phase_fd/integrated/tile_boundary_floor/gaps
timeout 10s prlimit --as=134217728 --cpu=10 --fsize=1048576 -- \
  python3 -IB "$u/tradeoff.py" --new-output-dir "$NOVA_SAIDA"
cmp "$u/tradeoff-receipt.json" "$NOVA_SAIDA/receipt.json"
```
