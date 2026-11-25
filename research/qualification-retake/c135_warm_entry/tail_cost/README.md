# Que duração por camada CPU elimina a margem das 378 entradas?

**2,861 ms por grupo CPU com READ obrigatório fecham o cenário de serviço C135 a 1×.** Com 378 entradas adicionais, os READ conservados a 80% precisam de um sufixo universal muito maior para fechar o mesmo orçamento, **56,320 ms** por grupo. O tempo real desse sufixo permanece **INCONCLUSIVE**. O critério exige trabalho CPU que só pode começar depois do último READ útil do grupo e que tem de terminar antes de o próximo grupo começar. O cálculo usa grupos (call, camada), separando os 5 dos 148 tokens. Uma medição de um tile CPU0 pode testar a marca temporal. Demonstrar a duração universal exige cobrir os últimos consumidores possíveis e as suas geometrias. [Pré-registo](protocol.md) · [Recibo integral](evidence/receipt.json)

| READ debitados | Escala dos READ | Piso com sufixo gratuito | Grupos CPU não vazios no ótimo a τ=0 → no corte | Maior τ admissível por grupo | Primeiro µs inteiro que fecha |
|---|---:|---:|---:|---:|---:|
| CPU e CUDA | 1 | 2,35487125 s | 26 → 23 | 2 860,551522 µs | 2 861 |
| CPU e CUDA | 0,8 | 1,88389700 s | 26 → 6 | 56 319,672500 µs | 56 320 |
| Só CPU | 1 | 0,80880550 s | 22 → 6 | 242 004,322500 µs | 242 005 |
| Só CPU | 0,8 | 0,64704440 s | 22 → 6 | 274 506,939167 µs | 274 507 |

**FORMAL no cenário especificado e TRACE_DERIVED nos preços.** Para cada número alcançável de grupos CPU com leituras `n`, calculámos o menor custo de READ `R(n)` sobre as distribuições possíveis de 378 entradas globais e das 16 identidades desconhecidas nas camadas de origem. O piso a minimizar para cada τ é `a × R(n) + n × τ`; o maior τ admissível é o máximo de `(2 427 104,435 µs − a × R(n)) / n` entre os n positivos. O mínimo número de grupos CPU com leituras é **6**. Para a escala 1 com ambos os tiers debitados, reduzir a população a seis já custaria 2,611483 s só em READ. Com 23 grupos, os READ precisam de pelo menos 2,36131175 s. Estes valores mostram por que a colocação ótima muda e por que a margem de 72,23 ms a τ=0 não deve ser repartida por uma contagem fixa de camadas. O cálculo preservou também a curva completa `R(n)` em quartos de µs. [Hipóteses de entrada e identificação das leituras](../README.md)

A geração pode ser toda servida pelo estado inicial. Um grupo sem chaves frias recebe sufixo gratuito. Nos restantes, o serviço continua a ser o maior de soma das cadeias/4 e maior cadeia individual. As duas últimas linhas oferecem todos os READ CUDA; nas quatro linhas todo o sufixo CUDA é gratuito. Com 2 860 µs e 2 861 µs, a primeira linha dá respetivamente 2 427 091,75 e 2 427 114,75 µs, lados opostos do orçamento de 2 427 104,435 µs do próprio C135. A hipótese layer-major impede sobrepor grupos, concede todas as rotas e o estado favorável e mantém três READ em série por chave. O modelo não estabelece uma velocidade do SSD nem um limite para um executor que altere essas precedências. Sem um preço de computação defendido para todos os grupos relevantes, ficam os pisos a τ=0 da tabela e a condição quantitativa acima. M3 PARTIAL, M4 NOT_MET.

Protocolo `e8229106`, código congelado em `d0f084db`, checkout de confirmação `dddc009061692d248554ba1b2f4ed0b7132dcd97`. R01 e R02 demoraram 2,65 e 2,60 s, com 85 720 e 85 820 KiB de RSS. Os dois recibos coincidem nos 6 610 B, SHA-256 `503ba5784b924d19139cd6e338d03abe30a0fd1db9725e0d0c9d4ba710742416`. Três testes passaram, incluindo 768 confrontos da programação dinâmica com enumeração exaustiva, reatribuição de créditos no corte e casos com custo zero, sem preço finito e já inviável. Sem pesos, forwards, GPU ou medição de operadores. [Implementação](screen.py) · [Contraprovas](test_screen.py)

```sh
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B research/qualification-retake/c135_warm_entry/tail_cost/screen.py \
    --repo "$PWD" --trace "$C135_TRACE" --pr45-checkout "$PR45" --new-output-dir "$NEW_OUT"
```
