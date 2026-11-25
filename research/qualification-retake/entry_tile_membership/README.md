# Antecipar os experts que reaparecem na última tile

**NO_GO nas curvas de desenvolvimento C294 para a preparação orientada pela última tile.** No nominal, a regra de reaparição seleciona **zero** experts ausentes de I. Em código, prepara 16 e encontra 13 primeiras faltas obrigatórias. Mesmo alargando a seleção a *todos* os experts da última tile ausentes de I e concedendo preparação e retenção gratuitas, os quatro braços excedem 5,333333 s nas duas escalas. Este resultado encerra o investimento num novo forward de C304 para observar esta regra. O desempenho que teria nas duas conversas C304 continua desconhecido. M3 PARTIAL e M4 NOT_MET. [Pré-registo](protocol.md) · [Recibo de avaliação](evidence/receipt.json)

| Braço C294 | Reaparição, candidatos CPU/CUDA e faltas encontradas | Todos na última tile, candidatos CPU/CUDA e faltas encontradas | Reaparição 1× / 0,8× (s) | Todos 1× / 0,8× (s) | Excesso de «todos» a 0,8× (s) |
|---|---|---|---:|---:|---:|
| Nominal 2 | 0/0 → 0 | 30/0 → 14 | 7,336 / 6,223 | 7,312 / 6,204 | 0,871 |
| Nominal 3 | 0/0 → 0 | 30/0 → 14 | 7,390 / 6,278 | 7,373 / 6,264 | 0,931 |
| Código 2 | 16/0 → 13 | 97/3 → 83 | 8,584 / 7,231 | 8,122 / 6,861 | 1,528 |
| Código 3 | 16/0 → 13 | 97/3 → 83 | 8,602 / 7,247 | 8,125 / 6,866 | 1,533 |

Dois processos de seleção produziram o mesmo selo a partir dos quatro WRT1. Os ranks OFF e ON e os 1 440 slots de I coincidiram por caso. A máscara de cinco bits de cada expert identifica a presença nas tiles de 32+32+32+32+25 posições da chamada incremental 9. A regra principal exige uma presença anterior, depois pelo menos uma tile sem uso e por fim presença na última. A camada 35 abstém-se porque calcula só a linha de saída. O leitor autenticou os WRT1 integralmente por SHA e só interpretou os registos anteriores ao retorno da chamada 9 para escolher as chaves. A fase de seleção pode ser executada apenas com a família WRT. [Escolhas e máscaras seladas](evidence/selection.json) · [Recibo de seleção](evidence/selection-receipt.json)

Os processos de avaliação abriram os quatro journals C294 após verificarem o selo. Conservam o restante fixo de C295 e os tempos individuais das três leituras seriadas de cada primeira falta sem preparação. Em cada barreira recomputam o máximo dos READ restantes. Sem seleção, o replay reproduz as 779/928 primeiras faltas e os pisos anteriores. No conjunto generoso, as 14 faltas encontradas no nominal retiram apenas 24,234/16,685 ms desse caminho à escala original. As 83 em código retiram 538,206/546,210 ms. A maior escala de READ compatível com 32/6 s, mantendo o mesmo restante, seria 0,643/0,632 no nominal e 0,558/0,557 em código. As curvas dispensam limite de slots durante o decode, materialização, faltas induzidas e reposição terminal. O orçamento compara passos fornecidos e deixa a qualificação do pedido natural para o seu próprio protocolo. [Piso de referência](../primary_backing/README.md) · [Cobertura do incremento nas conversas C304](../c304_causal_entry/protocol.md)

## Reprodução

Protocolo `7a3f2fe1`; código de medição `6a83ce490fff6ac2b4edf03fe120292aa92fc0f0`, árvore `96642e86749531df9c69339f328559a9a79f8792`. Os dois selos têm 11 288 B e SHA-256 `7ff26c591d9c79d8a8d61e6e2fb8a07b3cee8ab56793188d83230b5e471ddb5b`. Os recibos de avaliação idênticos têm 13 812 B e SHA-256 `d165bb2db43f1bf868cfcc925097a37faa31e43b5986bef0d518891c4660ba66`. As seleções demoraram 0,34 s cada e usaram 53 864/53 788 KiB de RSS máxima. Cada avaliação demorou 2,05 s e usou 141 584/141 264 KiB. Três testes sintéticos verificam o corte do leitor, a lacuna entre usos e a mudança do último READ do grupo. Zero modelo, GPU ou nova recolha física.

```sh
tool=research/qualification-retake/entry_tile_membership/screen.py
export LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python3 -B -m unittest discover -s research/qualification-retake/entry_tile_membership
timeout 120 python3 -B "$tool" --phase select --family "$WRT_FAMILY" --new-output-dir "$SELO_NOVO"
timeout 120 python3 -B "$tool" --phase evaluate --raw-dir "$TESY_C294_RAW" \
  --sealed-selection "$SELO_NOVO/selection.json" \
  --selection-sha256 7ff26c591d9c79d8a8d61e6e2fb8a07b3cee8ab56793188d83230b5e471ddb5b \
  --new-output-dir "$RESULTADO_NOVO"
```
