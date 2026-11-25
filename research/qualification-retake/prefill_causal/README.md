# Preparar a cache durante a conversa anterior

**NO_GO para substituir a retenção de R0 por frequência cumulativa e recuperar o conjunto de experts à entrada de decode.** Nos incrementos de 153 tokens a política reduziu as cargas contra R0 em 11,60% no nominal e 0,095% em código. Partiu de 40 slots vazios por camada e pagou também o prefixo. O custo mínimo de restaurar I excedeu a vantagem em ambos os casos. [Gate congelado](protocol.md) · [Resultados por braço OFF/ON](evidence/receipt.json)

| Caso e política | Prefixo | Incremento | Reposição mínima em I | Total |
|---|---:|---:|---:|---:|
| Nominal · R0, ambos os braços C294 | 3 570 | 1 043 | 0 | 4 613 |
| Nominal · ablação por recência | 3 592 | 1 082 | 0 | 4 674 |
| Nominal · frequência | 3 515 | 922 | 268 | **4 705** |
| Código · R0, ambos os braços C294 | 3 019 | 2 106 | 0 | 5 125 |
| Código · ablação por recência | 3 007 | 2 195 | 0 | 5 202 |
| Código · frequência | 2 999 | 2 104 | 372 | **5 475** |

Todos os números são admissões de 13 219 200 bytes de payload lógico. Os custos das duas políticas são SIMULADOS sobre rotas do target. R0 é TRACE_DERIVED das publicações nativas e snapshots. As réplicas OFF/ON da família de observação autenticam as duas sequências de trabalho. As contagens R0 dos braços históricos 2 e 3 de cada caso coincidem e são identificadas separadamente no recibo. No total, a frequência custaria **mais 92 cargas no nominal e 350 em código**. Neste último, a política poupa duas cargas no incremento porque a redução de 37 cargas CUDA quase cancela o aumento de 35 na CPU. Pressupor que todos os acertos custam o mesmo é uma relaxação para a triagem de bytes.

A ablação usa o mesmo planeador, protege os mesmos grupos e tem a mesma capacidade. Só o critério de escolha de vítima muda. Votos e recência avançam com os ranks realmente vistos, depois da admissão de cada wave. Ambas as políticas começam no processo vazio, pagam a transição de P para I e podem estacionar de graça as posições sem trabalho. Repor o conjunto em I conta os membros de R0 que faltam em cada pool. Atribuição a slots, gerações, cópias, cache auxiliar e paridade numérica ficam por qualificar. O journal detalhado só começa após P. Para contar as cargas R0 antes de P verificámos no manager pinado a inicialização de gerações a zero, a exclusão de vítimas LOADING e a única transição a READY após o serviço. Um snapshot sob mutex exige drain sem erro. A soma das gerações de P reconcilia com misses mais preloads. Em P→I, o verificador acompanha reserva, três leituras e cópias e publicação por geração. [Comparador R0](r0.py) · [Fonte e controlos do planeador](plan.py)

Confirmação na árvore limpa 1909d5cda24e5521d84c20ede1d51de3405fbf5f, pré-registo ec38519e. Duas reproduções, 1,34/1,26 s e até 91 324 KiB RSS, emitiram o mesmo SHA-256 5e0aebdcb3fb3b5e2de22fefd145954b3aa5defc1b5ccdfc535e0fb86c4e9c87. Nove testes locais. Nenhuma leitura de pesos ou geração de tokens. A hipótese de continuar os 32 passos com a cache produzida, sem reposição em I, é tratada pela [unidade seguinte](../prefill_causal_continue/protocol.md).

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120 prlimit --as=805306368 -- \
  python3 -B research/qualification-retake/prefill_causal/plan.py \
  --family "$WRT40" --historical-results "$C7/results" --new-output-dir "$NEW_OUT"
```
