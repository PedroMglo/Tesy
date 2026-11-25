# O operando pós-atenção antecipa cerca de três dos quatro experts da camada seguinte

Na captura C270, reutilizar a ativação pós-atenção e projetá-la pelo gate da camada seguinte recuperou **77,64% dos experts de prefill nos destinos CPU e 75,89% nos destinos CUDA**. A duas camadas de distância o recall foi 67,65% e 67,62%. Ambos os horizontes passam o crivo de sinal definido antes da execução. A pergunta de serviço permanece aberta: quantos desses acertos correspondem a faltas reais para as quais os bytes podem chegar antes do consumo? [Pré-registo](protocol.md) · [Resultados completos e distribuições 0–4](receipt.json)

| Horizonte | Fase | Destino | Linhas | Experts certos / pedidos | Recall | Mesmos números de expert da camada fonte | Linhas com todos os quatro experts previstos |
|---|---|---|---:|---:|---:|---:|---:|
| +1 | Prefill | CPU | 2 232 | 6 932 / 8 928 | 77,64% | 3,19% | 714 |
| +1 | Prefill | CUDA | 931 | 2 826 / 3 724 | 75,89% | 2,85% | 281 |
| +2 | Prefill | CPU | 2 139 | 5 788 / 8 556 | 67,65% | 2,30% | 361 |
| +2 | Prefill | CUDA | 931 | 2 518 / 3 724 | 67,62% | 3,25% | 174 |
| +1 | Decode | CPU | 96 | 313 / 384 | 81,51% | 2,86% | 38 |
| +1 | Decode | CUDA | 44 | 155 / 176 | 88,07% | 2,27% | 25 |
| +2 | Decode | CPU | 92 | 262 / 368 | 71,20% | 3,53% | 18 |
| +2 | Decode | CUDA | 44 | 152 / 176 | 86,36% | 4,55% | 23 |

O recall conta a interseção dos dois conjuntos de quatro experts no mesmo token e destino; a ordem exata e a distribuição dos hits estão no recibo. A coluna da rota fonte é um controlo fraco porque o mesmo número em camadas diferentes identifica matrizes distintas. Um controlo mais informativo usa a **última rota da própria camada alvo** quando a posição anterior já terminou e foi observada. No prefill, isso só acontece para a primeira linha da tile final. No decode há referência imediatamente anterior para 189 e 190. Cada par abaixo usa precisamente as mesmas linhas. [Definições e cobertura](../protocol.md)

| Fase | +1 CPU, projeção / recência | +1 CUDA | +2 CPU | +2 CUDA |
|---|---:|---:|---:|---:|
| Prefill | 62,50% / 30,21% (24 linhas) | 77,50% / 32,50% (10) | 52,17% / 30,43% (23) | 67,50% / 32,50% (10) |
| Decode | 79,17% / 48,44% (48) | 88,64% / 37,50% (22) | 69,02% / 49,46% (46) | 90,91% / 37,50% (22) |

**Calibração.** O controlo F32 anterior permanece inconclusivo em duas reproduções. A nova identidade troca somente a precisão dos dois operandos dos GEMM CUDA largos na simulação CPU, arredondando a dez bits de fração com empate para par e acumulando em F32. Nas outras formas manteve-se o cálculo anterior. Na própria camada, os **3 400 quartetos ordenados** coincidem com o router C270, incluindo a posição 6 da camada 25. O maior erro absoluto nos logits pré-bias de prefill CUDA caiu de 0,00128460 para 0,00016260; 117 482 dos 119 168 valores ainda têm bits diferentes. Nas quatro probabilidades por linha, a reconstrução com scores **arquivados** apresentou erro absoluto máximo de 1,79×10⁻⁷; com os scores projetados, 7,57×10⁻⁶. Os 13 600 pesos nativos foram preservados como referência. A observação sustenta esta avaliação de escolha de experts; o algoritmo cuBLAS efetivamente executado permanece indeterminado. [Controlo inicial](../README.md) · [Arredondamento, despacho e comparação](score.py)

**Próxima decisão.** O C309 físico já demonstrou que um preditor de chaves CPU em decode pode recuperar muitas faltas e, ao mesmo tempo, aumentar o custo do pedido. O ensaio presente cobre outro ponto do grafo, a tile de prefill e os dois tiers. Para testar se merece integração, selar os conjuntos previstos na própria conversa antes do router autoritativo e medir, por tile/camada, interseção com as chaves ausentes, ofertas sem uso, disponibilidade da ativação, deadline, bytes de staging/SET e contenção dos quatro leitores. O controle deve conservar os slots/gerações, os 47 tokens, os batches e o relógio do cliente. Há 368 640 multiplicações por posição e camada alvo. Transferir a ativação de 11 520 B por posição entre GPU e CPU pode consumir parte da antecedência. O tempo do verificador offline inclui leitura, validação, três horizontes e produção de recibos; não serve como preço do preditor integrado. Nenhuma latência do pedido foi medida aqui. [C309](../../../C309-UNTRAINED-STAGING-COST-NO-GO-20261007.md) · [Primeiro final e preço exterior](../../igpu_resident_rank/request_budget/device/pack_native/natural_trace/prefill_retention/repeat/README.md)

**Reprodução.** Protocolo `ea36e532`, código `a2485e2f`. Dois processos independentes, 0,45/0,46 s e 150 964/151 164 KiB RSS. Recibos SHA `edaea21eeca1913f2734cd1b790a83d1b27ab23c1a6a8074bd0345efdc14b64c`. Ambos reabriram os 69 parâmetros C299 e os 39 parâmetros do bundle privado previamente verificado; zero bytes requisitados ao GGUF. O operador de referência é o CPU NumPy 2.5.3 com um thread BLAS. Os testes incluem sinais, zeros, subnormais, empates, carry de expoente e exclusão dos sites CPU/singulares do arredondamento. [Testes](test_score.py)

```sh
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  timeout 90 prlimit --as=536870912 -- "$TESY_REPO/.venv/bin/python" -IB "$UNIT/tf32/score.py" \
  --part23 "$ARCHIVE/part-23" --c7 "$TESY_REPO/c7-native-placement-screen-20260927-1117utc" \
  --bundle /tmp/tesy-router-lookahead-diagnostic-20261125-r01 --new-output-dir "$NEW"
```
