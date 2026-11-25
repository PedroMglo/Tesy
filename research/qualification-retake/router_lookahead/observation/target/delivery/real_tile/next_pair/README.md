# Primeira tile C292: as 92 ofertas tiveram consumidor

**Nenhum dos 23 pares CPU adjacentes 1→2 a 23→24 oferece a contraprova procurada.** Cada votação das 32 posições permitiu quatro ofertas. Nas oito waves do destino, todas as 92 surgiram na procura E10 de uma geração e no top-4 oficial E27. O par 0→1 recuperou separadamente as quatro ofertas 42/19/56/113 e os seus quatro consumidores. O gate verificou ainda a presença das entradas de índice e dos ficheiros de referência C270 para todas as camadas examinadas. [Enumeração por par](receipt.json) · [Pré-registo](protocol.md)

Isto encerra a seleção por falso positivo **na primeira tile fria**. Não demonstra entrega a tempo, eliminação de uma segunda leitura, custo líquido de cada acerto nem cobertura no T2 natural. Não houve par a materializar: a verificação byte a byte de novos golds por par, a preparação dos parâmetros e a leitura de pesos ou biases do pack ficaram por executar. Para estudar desperdício real é preciso outra tile com uma proposta anterior ao destino que este não consuma, os seus próprios golds por posição e uma maneira de restabelecer a residência, a fila e as gerações nesse corte. O estudo anterior de todas as seis tiles encontrou 141 ofertas sem uso em 562 ofertas do prefill CPU; esse denominador inclui as outras cinco tiles. [C292 e prazos](../../../numeric/windows/README.md)

Protocolo `756960b3`, fonte `333a6aa4`. Duas execuções reabriram o C292 ON selado, os 7 768 quartetos de toda a captura, os E33/E34 e o índice C270 independente. Os recibos de 5 047 B são idênticos, SHA-256 `cf5cd619afee7baa118284a8a35aae65296b0eb549844f64c57744c5df306b03`. Cada processo durou 0,35 s e usou 79 188/79 132 KiB de RSS. Dois testes sintéticos e o Ruff passaram. [Código](screen.py) · [Testes](test_screen.py)

```sh
python3 -IB "$UNIT/test_screen.py"
nice -n 10 taskset -c 4 timeout 60 prlimit --as=536870912 --cpu=60 -- \
  python3 -IB "$UNIT/screen.py" --part23 "$ARCHIVE/part-23" --part116 "$ARCHIVE/part-116" \
  --c7 "$C7" --bundle "$BUNDLE" --manifest-dir "$DERIVED" --new-output-dir "$NOVO"
cmp "$NOVO/receipt.json" "$UNIT/receipt.json"
```
