# Quanto tráfego permite mudar apenas as vítimas da cache?

**NO_GO para seis passos/s nos dois casos C294 com 40 slots por camada, o prefixo histórico e apenas os experts que R0 já recebeu durante o prefill.** A melhor escolha possível de vítimas, conhecendo os 32 passos seguintes, ainda exigiria pelo menos 580 cargas no nominal e 547 em código. O link bruto de 10 Gbit/s comporta 504. Estas contas favorecem o candidato com zero tempo de cálculo, cópia, arbitragem, coordenação e cleanup. A referência é o serviço direto do GGUF original que está no USB. [Custo do transporte e observação do link](usb.md) · [Recibo do limite](cache-final-evidence/receipt.json)

## Da agenda observada às duas decisões

Cada passo fornecido contém as rotas autoritativas das 36 camadas e quatro experts distintos por camada. As chaves (camada, expert) impedem a reutilização de pesos de camadas diferentes. Cada carga transfere três componentes de 4 406 400 B. As duas repetições de cada caso têm sequências idênticas de conjuntos de rota e limites iguais. A tabela preserva as quatro identidades físicas. [Primeiro congelamento](cache_bound_protocol.md) · [Limite com início gratuito](cache-evidence/receipt.json)

| C294 trace-ON, 32 passos | Cargas R0 observadas | Início real, mínimo 40/camada | Início real, retenção ilimitada | Melhor início com experts vistos e 40/camada | Melhor início com experts vistos e 1 440 slots partilhados | Melhor início gratuito irrestrito, 40/camada |
|---|---:|---:|---:|---:|---:|---:|
| nominal153-2 | 1 081 | 787 | 779 | 580 | 549 | 181 |
| nominal153-3 | 1 081 | 787 | 779 | 580 | 549 | 181 |
| code153-2 | 1 308 | 928 | 928 | 547 | 435 | 306 |
| code153-3 | 1 308 | 928 | 928 | 547 | 435 | 306 |

**Primeira decisão.** Há 1 411 slots residentes e 29 vazios ao entrar em decode em cada braço. Dos experts que a conversa vai selecionar pela primeira vez ou reutilizar nos 32 passos, faltam 779 distintos no nominal e 928 em código. Mesmo com retenção ilimitada depois desse ponto, o teto é 3,884 e 3,261 passos/s respetivamente. Para chegar a seis no mesmo link, pelo menos 275 e 424 identidades servidas por USB teriam de chegar antes dessa janela ou estar disponíveis noutro tier. Uma política de vítimas, um dispatcher mais rápido ou uma nova ordem para as mesmas leituras durante o decode deixa esta obrigação de transporte. [Protocolo da fronteira](cache_boundary_protocol.md) · [Reconstrução dos 1 440 slots](cache_boundary.md) · [Recibo de entrada real](cache-paid-evidence/receipt.json)

**Segunda decisão.** Entregar ao candidato, gratuitamente, tudo o que R0 tinha no fim do prefixo ou publicou no prefill de 153 aumenta o universo elegível para 2 069 identidades no nominal e 2 677 em código. Com retenção ilimitada desde o fim desse prefixo, continuam por ver 549 e 435 identidades do decode. No nominal, este piso excede o limite em 45 cargas mesmo permitindo colocação entre camadas e dispositivos sem custo. Uma segunda prova dispensa o simulador. Para cada camada, dos D experts distintos do decode, só podem entrar gratuitamente até min(40, número de D já disponíveis). Somando a diferença nas 36 camadas, o piso é 577 no nominal e 544 em código, suficiente para a mesma exclusão. O simulador cobra ainda os conflitos de residência durante o decode. Com 40 slots por camada, as 580/547 cargas correspondem a tetos de 5,217/5,532 passos/s. Em código a relaxação dos 1 440 slots partilhados admite 435 cargas no limite ideal, teto de 6,956 passos/s. Esse ponto depende de colocação gratuita que usa o futuro e de transferências entre tiers sem custo. Falta uma agenda causal executável que prepare o estado e suporte prefill, decode e recursos no mesmo pedido. [Protocolo do intervalo](cache_span_protocol.md) · [Limite de identidades distintas](cache-span-evidence/receipt.json) · [Limite com capacidade finita](cache-final-evidence/receipt.json)

Com um inventário inicial livre para incluir experts nunca vistos no prefixo ou no prefill, 40 slots por camada permitiriam 181/306 cargas com previsão perfeita. Mesmo nessa relaxação, o primeiro número de slots uniforme que cabe na banda bruta é 30 no nominal e 35 em código. Para a pool partilhada, os primeiros totais são 1 068 e 1 230. Produzir o estado antecipadamente desloca leituras para o prefixo/prefill e disputa capacidade com ativações, KV e os outros experts. A classificação **INCONCLUSIVE** aplica-se à viabilidade de um candidato causal que mude esse estado. O R0 comparável em NVMe, a sessão natural e M4 mantêm os seus próprios critérios.

## Comparação com o transporte comprimido já medido

A conta mais favorável com 40 slots e o inventário observado ainda exige reduzir o payload médio das 580 cargas nominais em pelo menos 13,05%, ou o das 547 de código em 7,80%, para caber no link bruto. As percentagens usam o orçamento contínuo em bytes, antes de descontar o alinhamento. Na amostra de 64 experts de C319, Zstd nível 1 poupou 4,46% nos pesos alinhados CPU e 4,32% nos CUDA. Mesmo estender o melhor rácio amostrado de 0,910966 a todas as cargas nominais ficaria aquém do necessário nesse cenário. A amostra não mede o rácio de cada expert desta trajetória e a reconstrução também consome tempo. O resultado orienta o investimento na preparação da residência anterior ao pedido. [Caracterização de C319](../C319-LOSSLESS-COMPRESSIBILITY-NO-GO-20261007.md)

## Algoritmo e verificação

Cada procura obriga a manter simultaneamente os quatro experts escolhidos pelo router. Entre os residentes restantes, servir uma falta expulsando o expert cujo próximo uso é mais distante minimiza o número de inserções com custo unitário. O argumento de troca substitui uma expulsão de uso mais próximo pela de uso mais distante. Até ao próximo uso do primeiro expert a segunda escolha satisfaz as mesmas procuras e pode recuperar o outro expert quando necessário. Para um estado inicial escolhido gratuitamente, o mesmo argumento troca um residente de uso tardio por uma identidade elegível necessária mais cedo. A lista de vítimas exclui todas as seleções da rota atual. O verificador compara estas três condições de início com a enumeração independente de estados iniciais e vítimas em pequenas sequências com pins simultâneos. A política usa apenas demandas efetivas e admite descarte e reposição sem overhead. [Algoritmo](cache_bound.py) · [Verificador da fronteira](cache_from_boundary.py) · [Testes por enumeração](test_cache_bound.py)

Para reproduzir, apontar C294_RAW à pasta que contém os quatro diretórios c294-*-on.native. Cada destino precisa de ser novo.

```sh
u=research/qualification-retake
python3 -B "$u/cache_bound.py" --raw-dir "$C294_RAW" --new-output-dir "$OUT/free"
python3 -B "$u/cache_from_boundary.py" --raw-dir "$C294_RAW" --new-output-dir "$OUT/entry"
python3 -B "$u/cache_from_boundary.py" --raw-dir "$C294_RAW" --include-prefill --new-output-dir "$OUT/span"
python3 -B "$u/cache_from_boundary.py" --raw-dir "$C294_RAW" --include-prefill --finite-prefill --new-output-dir "$OUT/finite"
python3 -B -m unittest discover -s "$u" -p test_cache_bound.py
```

As execuções custaram 0,89–0,98 s cada, com pico de 97 616 KiB RSS. Zero forwards, zero leituras de payload e zero GPU. Energia DESCONHECIDA. Cada hipótese foi registada antes de consultar o seu resultado. O primeiro protocolo tem SHA-256 f5da286e6307f3d618c2a78b5bd3ec0840178b101a995ba459000dca846907b1. A fronteira inicial tem 5a7fc42dc1b6f19761f766c414c13c28e4bc44372fa46b78826de8d8043a26b4. O pré-registo de retenção ilimitada tem 7b0b7f8d74dc47d27fe83c9d5eac9514fa6d57d5495fba05ab009c4c78f6e869 antes do aditamento de capacidade.
