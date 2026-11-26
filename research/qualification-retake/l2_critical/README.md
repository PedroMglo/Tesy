# Quanto tempo de decode pode poupar uma L2 alimentada depois do prefixo?

**NO_GO condicionado para alcançar seis passos fornecidos por segundo só por esta via.** No C294 nominal, mesmo uma L2 ilimitada e gratuita, inicialmente vazia ao fim do prefixo P, deixaria **8,128 e 8,170 s** para os 32 passos de decode. Em código ficariam **7,379 e 7,381 s**. O alvo exige no máximo **5,333 s**. Até na sensibilidade favorável de 0,8, o melhor braço nominal excede o orçamento em 1,524 s e o melhor braço de código em 0,933 s. [Pré-registo](protocol.md) · [Recibo dos quatro braços e doze controlos](evidence/receipt.json)

A tabela dá segundos de decode. A primeira coluna de tempos é MEDIDA no journal nativo C294 trace-ON. Em cada uma das três colunas seguintes, o primeiro número é o controlo C295 reproduzido e o segundo o cenário ideal da L2. A escala multiplica as durações dos serviços e conserva o restante trabalho. A taxa física do NVMe não foi variada nem medida neste replay.

| Braço C294 | Nativo (s) | Controlo / L2, escala 0,8 | Controlo / L2, escala 1 | Controlo / L2, escala 1,2 | Ganho à escala 1 |
|---|---:|---:|---:|---:|---:|
| Nominal 2 ON | 9,381 | 7,832 / 6,857 | 9,346 / 8,128 | 10,861 / 9,398 | 13,04% |
| Nominal 3 ON | 9,415 | 7,873 / 6,902 | 9,384 / 8,170 | 10,895 / 9,437 | 12,94% |
| Código 2 ON | 10,986 | 9,122 / 6,266 | 10,948 / 7,379 | 12,774 / 8,491 | 32,60% |
| Código 3 ON | 11,010 | 9,146 / 6,270 | 10,975 / 7,381 | 12,804 / 8,491 | 32,75% |

Cada repetição elimina as três leituras de um expert apenas quando uma geração anterior já publicou os seus bytes após P. O cenário nominal elimina leituras em 292 das 1 081 admissões e o de código em 690 das 1 308. No nominal isso poupa 3,570–3,618 segundos somados de workers, mas adianta a última publicação dos grupos em apenas 1,214–1,219 s de parede. Em código, 7,904–7,927 segundos de workers dão 3,570–3,594 s de parede. Em todos os braços, cada um dos 1 152 grupos tinha zero a quatro novas gerações e os quatro workers estavam livres à entrada do decode. A diferença entre os máximos por grupo reproduziu a diferença do simulador nas três escalas. As cópias para o tier primário, o custo residual até à publicação, as barreiras e a cauda mantêm os seus relógios. [Cenário C295 e calibração](../../C295-ACTIVATION-BYTE-SCENARIO-RESULT-20261006.md) · [Cobertura das admissões L2](../l2_read_admission/README.md)

O limite depende das durações, das rotas e da agenda primária fixas de C294. Concede capacidade e admissão gratuitas, e mantém as durações dos misses apesar da redução de contenção. Os relógios do staging C318 e da conversa natural E20 têm workloads e critérios próprios. Para testar se uma L2 já quente à entrada de P muda a decisão, é preciso identificar no prefixo os bytes que poderiam ter sido admitidos, impor uma cota de RAM e cobrar as leituras, cópias e tempo até P. Uma colocação que dependa de conhecer as procuras futuras continua um limite otimista. [Próximo teste com prefixo quente](retoma.md) · [Controlos e condições de C318](../../post-c320/README.md)

Duas reproduções na árvore limpa `0683e814014218d55df22a0150338413aefc5f60`, commit `8caa7bb013abcd2a735fc090478812838ebfbc6f`, emitiram o mesmo recibo de 13 918 B, SHA-256 `b5640a5fd78cc28c6b1b708a7cf532526fe1190d5222c6ec64a678315bef1ca3`. Demoraram 1,15/1,17 s e atingiram 105 912/106 200 KiB de RSS. Três testes sintéticos verificaram a publicação anterior, um hit fora do caminho crítico, a mudança da última geração e a rejeição de serviços incompletos ou sobrepostos entre grupos. Zero pesos, forwards e GPU.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120 prlimit --as=536870912 -- \
  python3 -B research/qualification-retake/l2_critical/screen.py \
  --raw-dir "$C7/results/c294-feature-ready-service-window-20261006/raw" --new-output-dir "$NEW_OUT"
```
