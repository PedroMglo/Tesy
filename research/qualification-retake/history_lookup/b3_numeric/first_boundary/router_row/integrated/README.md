# O router volta à trajetória AR até à camada 24 nas posições com referência

A projeção em três colunas individuais no grafo real recuperou os **885/885 tensores observados das camadas 0–13 e da entrada**, nas três posições do bloco. Nas camadas 14–24, recuperou também os quatro estágios do router nas duas posições com referência. O primeiro desvio observado em ON está nos logits do router da camada 25. O KV pós-bloco e os quatro vetores finais continuam diferentes de AR. A condição para adquirir a terceira posição das últimas 22 camadas ficou por cumprir. [Recibo reproduzido](receipt.json) · [Pré-registo](protocol.md)

| Testemunho | OFF perante B3 histórico | ON perante AR independente |
|---|---:|---:|
| Ficheiros do prefill 189 | 2 248/2 248 iguais | 2 248/2 248 iguais |
| Pool e KV à entrada | ambos iguais | ambos iguais |
| Fronteiras da entrada e das camadas 0–13 | 885/885 iguais | 885/885 iguais |
| Linhas do router com todos os quatro estágios iguais | 42/42 com referência B3 | 64/86 com referência AR |
| Top-4 ordenado, em IDs comparados | 168/168 iguais | 344/344 iguais |
| Padrões F32 dos logits do router | 5 376/5 376 iguais | 8 192/11 008 iguais |
| Padrões F32 dos scores com bias | 5 376/5 376 iguais | 8 192/11 008 iguais |
| Padrões F32 dos pesos dos quatro experts | 168/168 iguais | 256/344 iguais |
| Quatro vetores finais com 201 088 F32 cada | 4/4 iguais | 0/4 iguais |
| Argmax únicos dos quatro vetores | 4/4 iguais | 4/4 iguais |
| KV serializado após as três entradas | igual | diferente |

Ambos os braços adquiriram 108 linhas de router e 1 149 payloads de fronteira, num total de 19 394 688 B por braço. O controlo histórico B3 contém as 42 linhas das camadas 0–13. Para AR há 42 linhas nessa faixa e mais 44 do C270 independente nas posições 189 e 190. Faltam referências para a posição 191 das camadas 14–35. [Primeira captura](../../README.md) · [Operador da camada 0](../README.md) · [Verificador de posições e bytes](evaluate.py)

| Posição avaliada | Entradas F32 diferentes / 201 088 | Erro absoluto máximo | RMSE |
|---|---:|---:|---:|
| 189 | 201 085 | 0,127172 | 0,022571 |
| 190 | 201 087 | 0,102224 | 0,019727 |
| 191 | 201 087 | 0,121151 | 0,016657 |
| 192, continuação de uma linha | 201 084 | 0,102196 | 0,017800 |

Em ON, todos os 128 logits mudaram nas duas posições observáveis da camada 25. O log do carregador atribui a camada 24 à CPU e a 25 a CUDA0. O primeiro tensor observado nessa camada já é a saída do router. A ativação de entrada, a atenção e o residual entre os dois routers ficam sem testemunho direto neste par. Identificar o operador responsável exige pelo menos essa ativação de entrada ou os tensores anteriores. A igualdade dos IDs manteve a escolha ordenada dos experts nas 86 linhas observáveis, mas os pesos da mistura mudaram nas 22 linhas das camadas 25–35. O resultado fecha a intervenção isolada sob o contrato de igualdade dos logits e do estado.

## Proveniência e custo da qualificação

O build em 83093c4c reutilizou 165 dos 166 objetos, recompilou uma TU do construtor do grafo e preservou o conjunto e o tipo dos símbolos dinâmicos da candidata. O relink e o controlo recompilado reproduziram as secções carregáveis do original, excluída a nota de build-id. O cliente derivado passou o autoteste e a prova de 18 bibliotecas mapeadas no PID sem modelo. Build de 9,875 s, pico de 347 280 KiB segundo o máximo dos filhos. [Construtor](build.py) · [Intervenção no grafo](source.py)

O supervisor em 385c1366 obteve C55 de 62 amostras em 61,005 s, admitiu E20 e executou OFF e ON em processos separados, cada um com C118. Em ambos observou três FDs diretos do modelo, zero swap, pico GPU de 6 868 MiB e encerramento do processo e da unidade. O relógio nativo repartiu-se em 30,346 s OFF e 28,615 s ON. Os scopes incluindo a admissão demoraram 91,175 e 89,362 s, com picos de cgroup de 16 117 194 752 e 15 894 118 400 B. A família demorou 184,338 s e produziu 128 241 105 e 128 231 697 B de raw. São custos de aquisição de tensores com callbacks síncronos. O ensaio usa quatro entradas fornecidas sobre o prefixo fixo de 189 e não mede aceleração de conversa, confirmação especulativa ou rollback. [Supervisor](profile.py) · [Identidade de processo e DSO](binding.py)

A revisão offline autentica os dois braços, o monitor, a C118, os 2 248 ficheiros de prefill e o KV, e recalcula as quatro linhas finais e os payloads de fronteira. O recibo físico tem SHA 27b97866f3d452786860f42133ffb247a9f06d95c904473aa2b09533de16c086 e o compacto reproduzido tem SHA 1058221b6735fe7caaaf78f724e2c97b1b54c05983c3ed92bc989893de312aed. Para repetir com os raws arquivados, `PARTS` é a raiz privada das partes e `PAIR` o diretório da família terminada. [Revisor](review.py)

```sh
python3 -IB "$UNIT/review.py" --family "$PAIR" \
  --family-sha256 27b97866f3d452786860f42133ffb247a9f06d95c904473aa2b09533de16c086 \
  --archived-family "$PARTS/part-102/tesy-b3-first-boundary-physical-20261125-r01" \
  --original-family "$PARTS/part-32/tesy-b3-numeric-physical-20261125-r01" \
  --c270-dir "$PARTS/part-23/tesy-c270-driver-20261125-r01" --new-output-dir "$FRESH"
```
