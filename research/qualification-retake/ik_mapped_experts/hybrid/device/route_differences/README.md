# Rotas e logits do GGUF sintético de duas camadas

**REPRODUZIDO.** No mesmo prefixo, CPU e CUDA com os experts residentes
escolhem os mesmos quatro experts nos 66 sítios observados. A ordem muda
uma vez, na posição 7 da camada 0, de `[0,7,6,5]` para `[0,6,7,5]`.
Os 1 056 logits F32 diferem e há três posições em que muda o máximo único.
Nessas três posições, os quartetos têm a mesma ordem em ambas as camadas.
O máximo mantém-se na posição 7. Esta associação local deixa em aberto a
causa das diferenças, incluindo a propagação de estados de posições anteriores.

| Posição | CPU top-1 / top-2 (ID) | Margem CPU | CUDA top-1 / top-2 (ID) | Margem CUDA |
|---:|---:|---:|---:|---:|
| 13 | 9 / 28 | 0,005489 | 28 / 9 | 0,010753 |
| 25 | 28 / 31 | 0,007764 | 31 / 28 | 0,025083 |
| 29 | 28 / 31 | 0,018044 | 31 / 28 | 0,016195 |
| 32, token fornecido | 31 / 28 | 0,028491 | 31 / 28 | 0,032030 |

Cada margem é a diferença entre os dois maiores logits dessa linha. Os 33
máximos em cada braço são únicos. O prefill teve 29/32 máximos coincidentes
e o passo seguinte 1/1. O cliente fornece o token 7 nas 33 posições, com
o mesmo histórico em ambos os braços. Estes dados permitem comparar os
máximos calculados nesse histórico. Uma trajetória com amostragem ou geração
gulosa autorregressiva exigiria outra observação. Os scores do router
também seriam necessários para apurar empates entre experts.

**BANK9, DIAGNÓSTICO parcial.** Os 32 quartetos lógicos do prefill na camada
0 coincidem, na mesma ordem, com RESIDENT. A cópia de tensor com sufixo
`(cont)` contém as mesmas 32 linhas. O revisor contou somente o tensor
lógico. O processo parou em `rank shape`; faltam os restantes 34 quartetos
e as 33 linhas de logits. **BANK7 NOT_RUN.** A família R02 conserva
`FAIL_PRESERVED`. A equivalência numérica do banco permanece em aberto.

## Reprodução

Protocolo congelado em `4951c128`, após conhecida a discrepância agregada e
antes da leitura das linhas para este diagnóstico. O recibo discrimina as
posições por camada, a cardinalidade das interseções, os logits e margens
sem arredondamento nas quatro linhas da tabela e a cobertura parcial.
[Protocolo](protocol.md) · [Recibo](result.json)

A análise reabriu os originais e as cópias privadas das partes 133 e 136. As
duas saídas coincidiram byte a byte, SHA-256
`03e79960ff66e0540115491e11d169c0cbb6436ea91101dac39cb25a49b4ce8b`.
Executar na pasta deste revisor, com o diretório de arquivo em `ARCHIVE` e um
destino inexistente em `NEW_OUT`. Nenhum cálculo de inferência é necessário.

```sh
python3 -B score.py \
  --cpu "$ARCHIVE/part-133/tesy-ik-hybrid-client-cpu-20261126-r02" \
  --family "$ARCHIVE/part-136/tesy-ik-hybrid-device-20261126-r02" \
  --family-sha256 2e83262ce3efb72136f2025d76db749f21e768bc78b8abbe55480648dd9fa27a \
  --new-output-dir "$NEW_OUT"
cmp result.json "$NEW_OUT/receipt.json"
python3 -m pytest -q test_score.py
```
