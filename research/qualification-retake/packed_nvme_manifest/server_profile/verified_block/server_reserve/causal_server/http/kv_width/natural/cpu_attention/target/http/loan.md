# O custo de devolver o slot emprestado

**NO_GO para a regra causal de frequência e recência com um empréstimo por camada.** Para evitar 15 leituras originais, a regra fez 28 leituras de reparação. A chamada de 148 passou de 1 212 para **1 225 leituras**, mais 171 884 544 B de janelas alinhadas. As 7 497 posições consultadas e os 1 440 conteúdos e gerações no primeiro decode coincidiram nos dois braços. O resultado já perde no volume com as cópias e barreiras a custo zero. [Regra congelada](loan-protocol.md) · [Resultados por tile](loan-result.json)

| Tier | Capturas | Resgates | Reparações por leitura / no retorno | Controlo → candidato |
|---|---:|---:|---:|---:|
| CPU | 26 | 10 | 8 / 10 | 768 → 776 |
| CUDA | 14 | 5 | 3 / 7 | 444 → 449 |

Das 40 capturas, 25 nunca serviram a procura que tentavam antecipar. Só 12 empréstimos terminaram pela próxima sobrescrita normal do slot emprestado. Os restantes precisaram de recuperar o dono original. Pagar a entrada de decode acrescentou 17 reparações. Mesmo transferindo gratuitamente as 17 para fora da janela, os 15 resgates menos as 11 reparações anteriores só poupariam quatro leituras, 52 887 552 B. São precisas pelo menos 17 ou 28 no cenário mais favorável do filtro. A execução manipulou 727 056 000 B de payload lógico em capturas e resgates. A fixture de cópia anterior continua válida para a agenda de 35 escolhida com informação futura. [Ótimo da regra offline](slots.md) · [Custos medidos no portátil](slot_copy/README.md)

Os dois replays reabriram o T2 de P97 e P106, a agenda de 40 slots e os preços de cópia. As escolhas usam apenas frequências, recência e informação disponível na wave corrente. Um leitor inesperado, incluindo parking, encontra o dono original restaurado antes do seu uso. Cinco testes verificam resgate, substituição, leitura de parking, dívida no retorno e a independência de um sufixo ainda invisível. Para reabrir esta regra, a seleção ou a posse do armazenamento teria de mudar os acertos e as reparações cobradas. O filtro de decode tem um mecanismo e um preço independentes.

Protocolo `3521c738`, código `d1a6e6c2bc3f4d9cdbc72dc9517d1108c350ddf5`. Os dois resultados tiveram SHA-256 `f8a6216bc844862d81bd02f579e553bfa274c677d7f08b6acde3c0189a390068`, 1,64 e 1,62 s de parede, pico de 76,0 e 76,3 MiB de cgroup e zero swap. A parte 191 tem 12 644 B em quatro ficheiros. Zero inícios de modelo, GPU ou HTTP. [Verificador](loan.py) · [Manifesto](../../../../../../../../../../../private_archive/part-191.json)

```sh
python3 -IB "$HTTP/loan.py" --archive "$AR" --slots "$SLOT_REVIEW" --pricing "$COPY_REVIEW" \
  --capture "$CAPTURE" --verified "$VERIFIED" --plan "$PLAN" \
  --commit "$MEASUREMENT_COMMIT" --new-output-dir "$NEW"
```
