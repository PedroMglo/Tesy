# A entrada do router da camada 25 já diverge nas posições 189 e 190

Na continuação B3 de três tokens, a saída dos experts da camada 24 coincidiu com a referência de um token em todas as 2 880 coordenadas de cada posição emparelhada. A ativação normalizada que o router da camada 25 recebeu já diferia nas 2 880 coordenadas de ambas. **A primeira diferença observada com referência independente é agora `attn_post_norm-25`, antes do produto do router.** O resultado deixa em aberto quanto desvio adicional o próprio produto introduz. [Recibo reproduzido](receipt.json) · [Protocolo](protocol.md)

O campo `first` de `ON/comparison.json` conserva, por compatibilidade, a primeira diferença do observador anterior nos logits do router. O revisor autentica esse campo contra a parte 108 e combina os seus sítios com `gold_rows`, ordenados por camada e dependência. O campo `first_different_paired_cut` do compacto identifica o primeiro corte comparável nessa união, em cada posição. [Revisor](review.py)

| Tensor comparado com C270/C127 | F32 diferentes na posição 189 | F32 diferentes na posição 190 |
|---|---:|---:|
| Entrada normalizada do FFN, camada 24 | 0 / 2 880 | 0 / 2 880 |
| Saída dos experts, camada 24 | 0 / 2 880 | 0 / 2 880 |
| Entrada normalizada do FFN, camada 25 | 2 880 / 2 880 | 2 880 / 2 880 |
| Produto do router antes do bias, camada 25 | 128 / 128 | 128 / 128 |
| Saída dos experts, camada 25 | 2 880 / 2 880 | 2 880 / 2 880 |

A soma residual de saída de L24, a normalização de atenção de L25, Q, K, V, a saída de atenção e a entrada residual do FFN têm agora capturas válidas nas três posições B3. Falta a trajetória independente destas sete sondas antes de atribuir o desvio a uma operação. Na posição 191 faltam também as quatro novas referências dos FFN de L24/L25. Dos 33 novos tensores por posição e nome, oito têm par independente e 25 ficam sem esse par. O discriminante seguinte pode usar estes bytes B3 e obter apenas a referência de uma linha para os sítios adjacentes. [Cortes disponíveis](probes.py) · [Inventário do gold](../source_l25/README.md)

O observador preservou os 1 149 payloads do B3 ON anterior, as cinco linhas de 201 088 logits completos e finitos, o prefixo de 2 248 ficheiros, o KV e pool iniciais e o KV após as três entradas. A entrada e as camadas 0–13 voltaram a coincidir nos 885/885 payloads comuns a AR. O conjunto de fronteiras desta execução tem 1 182 payloads e 19 732 608 B. Os quatro vetores finais da família integrada continuam diferentes de AR. Esta aquisição delimitou uma falha de paridade em entradas fornecidas. O custo e o benefício de combinar o router por linha com outra intervenção na conversa continuam por medir. [Estudo integrado anterior](../README.md) · [Validador](grade.py)

## Reprodução e recursos

O build do cliente em `ec34fbbd` reutilizou a DSO de grafo anterior e recompilou uma unidade de tradução do observador. Os dois clientes passaram os autotestes sem modelo. O novo ELF tinha SHA-256 `1858c363a5e668ba9673b9be1295187aa91b0eeb8d01f2137b9d225bbf26be53` e os 18 objetos iniciais foram conferidos. O build demorou 4,204 s, com pico de 356 732 KiB nos filhos. [Construtor](build.py)

O supervisor congelado em `6b40c7c8` admitiu E20 após 62 amostras C55 em 61,022 s e uma C118 própria. O único processo B3 ON terminou com 29,201 s nativos, 89,903 s de scope e 94,034 s de família. O monitor registou três descritores diretos do modelo, 15 888 449 536 B de pico de cgroup, 6 868 MiB de VRAM, zero swap e 128 568 561 B de raw privado. Os relógios incluem observação síncrona e não qualificam desempenho do pedido. [Supervisor](profile.py)

O recibo físico tem SHA-256 `3f2e9ffdf46dcb2c68d6f4b515483f56068ef593feff214abab5e27911ff961d`. O revisor valida as identidades do braço, monitor, lançamento, C118, loader, protocolo e comparação. Reabre os bytes B3 e AR contra o gold C270/C127. As reproduções do original e da cópia da parte privada 110 produziram compactos idênticos com SHA-256 `750c49aad4b8d48cdfa2dde56182c9aea6edd1fc2fc08e9edabc8a9d2cd4e0cf`. O manifesto privado tem SHA-256 `ea5e194d093797754284c694d7f9de6bd63fb59d651fbfab94eee6fc9ebfb92b`. Os seis testes de contrato correm sem modelo. [Revisor](review.py)

```sh
python3 -IB "$UNIT/review.py" --family "$MEASURED" \
  --family-sha256 3f2e9ffdf46dcb2c68d6f4b515483f56068ef593feff214abab5e27911ff961d \
  --integrated-family "$PARTS/part-108/tesy-b3-router-integrated-physical-20261125-r01" \
  --archived-family "$PARTS/part-102/tesy-b3-first-boundary-physical-20261125-r01" \
  --c270-dir "$PARTS/part-23/tesy-c270-driver-20261125-r01" --new-output-dir "$FRESH"
```
