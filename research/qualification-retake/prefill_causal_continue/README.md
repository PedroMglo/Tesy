# Continuar o decode com os experts que o prefill reteve

**NO_GO para escolher vítimas pela frequência acumulada neste workload C294.** Manter no decode a cache produzida pelo incremento poupa 121 cargas durante o incremento nominal e duas em código, face a R0. Nos 32 passos seguintes custa mais 527 e 320 cargas, respetivamente. A política perde nos dois casos mesmo que a composição final dos pools seja gratuita. [Pré-registo](protocol.md) · [Recibo por braço, fase e tier](evidence/receipt.json)

| Caso | Política | Prefixo | Incremento | Decode | Repor conjunto final (mínimo) | Total com reposição |
|---|---|---:|---:|---:|---:|---:|
| Nominal | R0, braços 2 e 3 | 3 570 | 1 043 | 1 081 | 0 | 5 694 |
| Nominal | Ablação LRU | 3 592 | 1 082 | 1 074 | 50 | 5 798 |
| Nominal | Frequência | 3 515 | 922 | 1 608 | 574 | 6 619 |
| Código | R0, braços 2 e 3 | 3 019 | 2 106 | 1 308 | 0 | 6 433 |
| Código | Ablação LRU | 3 007 | 2 195 | 1 298 | 92 | 6 592 |
| Código | Frequência | 2 999 | 2 104 | 1 628 | 619 | 7 350 |

Cada carga representa 13 219 200 bytes de payload lógico. A soma incremento + decode teria de cair pelo menos 10% nos dois casos face a ambos os controlos, sem regressão no prefixo, no incremento ou no decode individual. Com frequência a soma aumenta **406/318 cargas** face a R0 (nominal/código) e **374/239** face a LRU. Até à reposição final, a diferença face a R0 chega a 925/917 cargas. A reposição cobra apenas a leitura das identidades ausentes para recuperar o conjunto de R0. Atribuir slots, copiar bytes e restaurar gerações pode ter custo adicional.

A simulação começa com pools vazios, conserva 40 slots por camada e atravessa o fim do incremento sem restituir o estado histórico. O target fornece 4 608 IDs ordenados por caso, quatro por camada em cada um dos 32 passos. Frequência e recência só avançam após a admissão da wave. Os quatro braços trace-ON históricos fornecem os custos R0 e as réplicas OFF/ON autenticam os inputs. O resultado fecha esta política de residência nas duas sequências fornecidas. O custo de E/S física, a latência do cliente e a exatidão de uma implementação no backend ficam por medir. [Antecedente com reposição no primeiro decode](../prefill_causal/README.md)

Pré-registo `5191a917`, confirmação em árvore limpa `979508a3e214787040c999201e127260c3b8f7e2`. Duas reproduções de 1,27 e 1,29 s, com até 91 280 KiB de RSS, emitiram o mesmo SHA-256 `ef9234d7d5b811ec3897e1eb3e62a6d727984f07d98a54bdede74042f132b8f8`. Orçamento por execução de 120 s, 768 MiB, uma thread e 10 MiB de saída. Zero pesos, forwards e GPU.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120 prlimit --as=805306368 -- \
  python3 -B research/qualification-retake/prefill_causal_continue/plan.py \
  --family "$WRT40" --historical-results "$C7/results" --new-output-dir "$NEW_OUT"
```
