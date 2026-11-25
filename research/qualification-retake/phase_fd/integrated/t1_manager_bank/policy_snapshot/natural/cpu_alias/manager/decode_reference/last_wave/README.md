# Primeira substituição observável no decode CPU0 da C270 R0

O expert **11** ocupava o slot **14**, geração **5**, imediatamente antes de a primeira chamada de decode reservar esse slot para o expert **24**, geração **6**. O expert 11 aparece ativo no slot 14 na wave 0 da última tile de prefill. Foi possível reconstruir o último proprietário dos 40 slots. A captura e a regra de reservas do pin sustentam a identificação. A geração anterior de 14 deduz-se do único incremento na sua reserva. [Recibo público](evidence/receipt.json) · [Prova das três entradas READY e da reserva seguinte](../prestate.md)

| Wave | Experts distintos | Ranks ativos | Ranks mascarados |
|---:|---:|---:|---:|
| 0 | 18 | 51 | 65 |
| 1 | 18 | 37 | 79 |
| 2 | 18 | 27 | 89 |
| 3 | 1 | 1 | 115 |
| 4 | 0 | 0 | 116 |
| 5 | 0 | 0 | 116 |
| 6 | 0 | 0 | 116 |

A tile final cobre as posições 160–188 da chamada de 189 tokens. Para as 29 posições e quatro ranks, a captura contém o top-k lógico com strides 4/512 e sete pares contíguos de IDs físicos e máscara. Cada uma das 116 ocorrências teve exatamente uma participação ativa. Cada rank mascarado produziu o sentinela −1 do backend CPU. Os 55 experts distintos aparecem na ordem de primeira utilização que C269 divide em grupos de até 18. O recibo privado inclui a última participação ativa por slot e os hashes de todos os 17 inputs da captura.

## Fundamento da identificação

No C269 `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`, `src/llama-graph.cpp` linhas 1964–1991 escolhe o pool por camada e constrói a quantidade de waves. Nas linhas 2171–2186 a próxima operação de IDs tem uma dependência explícita dos GEMMs da wave anterior. Em `src/llama-moe-stream.cpp` linhas 574–727 a procura de cada wave usa o seu grupo de experts. Toda antecipação pertence ao grupo imediatamente seguinte. Os slots exigidos ficam protegidos antes da antecipação e a operação de IDs aguarda a residência dos seus operandos. Com grupo corrente e seguinte vazios a wave só toma emprestados slots para parking. As linhas 733–864 associam cada rank ativo ao seu expert residente e preenchem a máscara. O modo CPU selado escreve −1 nos ranks excluídos. Assim, qualquer mudança posterior de proprietário nessa tile teria uma participação ativa posterior no mesmo slot. As restantes camadas usam pools próprios. [Verificador e identidades das fontes](screen.py)

O cliente C270, SHA da fonte `295e710af6efbd59944ae999911aeb94f0a7aef633895f1f3404161e56bdb0e6`, chama um prefill de 189 e depois 32 decodes unitários sobre o mesmo contexto, em `capture.cpp` linhas 570–597. O snapshot por expert da procura é recolhido sob o mutex nas linhas 200–227. Na primeira descodificação, os outros três experts pedidos estavam READY e mantiveram os seus slots. O único ausente, 24, provocou uma reserva. No C269, `reserve_slot_locked`, linhas 395–408, remove o dono anterior e incrementa a geração exatamente uma vez. O mapa e as cinco bibliotecas do processo R0 foram vinculados ao contrato da execução e ao seu manifesto de captura. [Referência FFN de uma posição](../README.md)

A fixture pode usar a substituição e11→e24 e os três hits e28/s3/g6, e8/s6/g5 e e16/s35/g4. A idade de utilização, o calor e as gerações dos outros 36 slots continuam por determinar. Uma fixture que condicione explicitamente o seletor deve declarar essa condição. A paridade dos 2880 F32 do FFN tem confirmação independente na referência C127. Esta reanálise mediu exclusivamente o tempo e memória do verificador offline.

## Reprodução e recusas preservadas

Na checkout limpa `70698f5aa6bf3cd96a9e739ac51831715d8021f2`, definir `D` como o diretório deste ficheiro, `LAB` como o diretório histórico que contém `backends/c269-layer-last-use` e `results/c270-last-use-ordered-fidelity-20261004`, e `PRESTATE` como a reprodução da fronteira de decode com recibo `9bc5d91831e50f4f8cacc73f5b34b02542c2c8b5010cb1e620f7ddb7d2101ec6`. Cada destino deve ser novo.

```sh
python -IB "$D/test_screen.py"
LC_ALL=C LANG=C OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -IB "$D/screen.py" --lab "$LAB" --prestate "$PRESTATE" --new-output-dir "$NEW"
```

A execução original de contagem com `--original-count` encontrou um `MemoryError` ao materializar o índice. O locale da estação mapeava 222 MiB em endereço virtual. Com `LC_ALL=C` e o mesmo limite de 256 MiB, a recusa seguinte verificou que o índice selado contém sete pares perante a exigência original de oito. Ambas terminaram antes de interpretar qualquer proprietário. A correção prospetiva usa a fórmula observada na fonte. A contagem de oito corresponde a tiles de 32 posições. [Protocolo original](protocol.md) · [Correção antes da inferência](geometry.md)

As duas repetições com a cardinalidade correta produziram o mesmo recibo privado de 8451 bytes, SHA-256 `bebcd9273232b6623a381b4eba8de87a7c48818bb82eaf9e6e8ec8b45f74a2aa`. Ambas levaram 0,08 s de parede, com 28 528 e 27 708 KiB de RSS máximo. O limite por processo foi de 60 s e 256 MiB de espaço de endereçamento. Cinco testes sintéticos cobrem geometria, sobrescrita, parking, conflitos de binding e corrupção da máscara. Houve zero leituras do pack e zero lançamentos de modelo.
