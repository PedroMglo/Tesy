# Quanto podem ganhar os dois bancos no pedido completo?

**Nenhum dos dois bancos chega aos 10 s até ao primeiro conteúdo final quando o efeito de libertar os workers termina na próxima fronteira drenada.** Esta conclusão já vale quando desaparece toda a duração das callbacks afetadas em CPU e CUDA, incluindo o trabalho de outros experts na mesma callback. Nesse cenário generoso, a recência ainda tem margem para 6 tokens/s de decode nas duas observações. A frequência de prefill deixa o decode abaixo da meta em ambas. [Protocolo anterior ao cruzamento](protocol.md) · [Recibo compacto com nanossegundos](receipt.json)

| Pedido e banco | Crédito máximo no primeiro final | Primeiro final restante | Crédito máximo no decode | Decode restante (47 saídas) |
|---|---:|---:|---:|---:|
| P106 · últimas 353 vítimas | 5,361 s | 14,168 s | 1,649 s | 7,565 s |
| P106 · frequência no prefill | 4,861 s | 14,668 s | 0,762 s | 8,452 s |
| P97 · últimas 353 vítimas | 5,421 s | 12,905 s | 1,643 s | 7,304 s |
| P97 · frequência no prefill | 4,902 s | 13,423 s | 0,768 s | 8,179 s |

Os dois objetivos aplicam-se ao mesmo pedido e o decode dispõe de 7,833 s para 47 saídas. As callbacks das 44 avaliações anteriores à amostra 45 participam de ambos os relógios. Cada coluna inclui esse intervalo uma vez. As duas últimas avaliações contam apenas para o decode. Não houve callback dessas avaliações já iniciada à chegada da primeira peça final, nas duas observações. Retirar também do P106 todos os 646,428 ms que o cliente passou antes de iniciar o stream de T2 ainda deixaria o primeiro final em pelo menos 13,521 s com recência ou 14,021 s com frequência. [Fronteira do cliente](../repeat/README.md) · [Custos comuns e exclusivos](receipt.json)

### Onde o banco poderia intervir

Conservámos as **2354 gerações**, os 7012 quartetos roteados, as 1440 entradas do primário e as 2987 callbacks. Houve 1263 cargas no prefill (808 CPU, 455 CUDA), 1067 no decode até à amostra 45 (773 CPU, 294 CUDA) e 24 nas duas avaliações seguintes (13 CPU, 11 CUDA). A recência cobre 327 cargas de 233 chaves; a frequência cobre 373 cargas de 244 chaves. Os bancos foram selados antes do segundo POST de P106. Em P97, que é uma repetição da mesma conversa, só transferimos as chaves depois de conferir as identidades por geração, slot e wave. Cada conta usa as durações do seu próprio processo. [Auditoria das gerações](../../jobs.py) · [Seleções e aquisição em T1](../README.md)

O limite com drenagem dá crédito integral às callbacks onde se reserva uma chave coberta e admite efeitos sobre outras callbacks enquanto LOADING, fila ou claims se prolongam. Em P106, a recência toca diretamente 91 callbacks no prefill e pode afetar mais 46; a frequência toca 119 e pode afetar mais 41. No decode, o crédito cobre diretamente 155 e 74 callbacks, respetivamente. A ablação de banco vazio produz zero nos dois relógios. O controlo que cobre as 1721 chaves de todos os jobs deixa margem para ambos os objetivos se o serviço for gratuito. As duas políticas de 353 lugares pagariam a aquisição em T1 e os custos de entrega e proteção em T2 numa implementação. Aqui esses custos são gratuitos. [Revisor](score.py)

### Se a influência sobreviver à drenagem

Há 2896 finais de callback drenados em cada traço. Para dispensar a premissa de que o candidato e o controlo reconvergem nesses pontos, o segundo cálculo permite eliminar *qualquer* callback a partir da primeira reserva coberta. Com todos os serviços a custo zero sobra margem nos dois relógios. Nesse envelope mais largo a exclusão do mecanismo **depende do preço do serviço residual**. Para o cobrar, entram apenas as gerações descobertas que a mesma callback reservou e foi obrigada a consumir prontas. As 1918 gerações com esse vínculo, antes da interseção com cada banco, tiveram primeiro enqueue de procura nos dois journals. Em cada callback os quatro workers obrigam a conservar pelo menos o maior preço individual encadeado ou um quarto da soma dos preços, o que for maior. A conta inclui READ e os três SET de cada job elegível, exclui preloads de outra wave e concede o restante trabalho gratuitamente. [Definição de preço](../../release/review.py)

| Influência até ao fim, primeiro final restante | READ + SET a metade do preço observado | READ + SET ao preço observado |
|---|---:|---:|
| P106 · recência / frequência | 11,965 / 12,007 s | 16,758 / 16,790 s |
| P97 · recência / frequência | 10,696 / 10,749 s | 15,482 / 15,539 s |

Mesmo com o efeito prolongado e a metade do preço, o primeiro final ultrapassa 10 s nas duas observações. Uma mudança que acelere os jobs descobertos para além desta sensibilidade, altere as reservas ou reduza contenção fora das callbacks requer outra medição. Os tempos dos SET terminam no retorno da chamada do worker. Estes dados não determinam quando o consumidor CUDA concluiu o trabalho nem quanto tempo ganharia uma cache efetivamente instalada. [Pressupostos e alternativas](protocol.md)

### Reprodução

Na checkout de medição `7f0212e174a9fb25d4db69410d974ce45a8c66bc`, correr em Bash a partir desta pasta. Cada processo exige um destino novo.

```bash
ARC=/mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01
for run in 01 02; do
  env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    /usr/bin/time -f 'elapsed=%e maxrss_kib=%M' timeout 60 prlimit --as=536870912 --cpu=60 \
    python3 -IB score.py --archive "$ARC" --new-output-dir "/tmp/tesy-full-bank-request-cost-20261125-r$run"
done
```

Os recibos completos coincidem byte a byte, SHA-256 `8c7d2c73abbe81bf3214f3f79cb7fd30fb21ec6c85078e93c42701730dbe0299`. As execuções duraram 1,42 e 1,45 s, com máximos de RSS de 62 164 e 60 840 KiB. Quatro testes sintéticos cobrem propagação e drenagem, banco vazio, preço em paralelo, preload sem dependência, interseção dos relógios e adulteração do arquivo. [Testes](test_score.py)
