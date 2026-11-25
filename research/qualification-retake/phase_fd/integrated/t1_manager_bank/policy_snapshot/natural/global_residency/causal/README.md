# A LRU global recupera 10 leituras no prefill e perde 121 no decode

**NO_GO para levar esta LRU à fixture de decode.** Com os mesmos pesos disponíveis antes do segundo pedido, o pool unificado de 1 262 entradas pediu **918 leituras de disco para 46 avaliações**. São 188 a menos que a mesma LRU limitada a 40 lugares por camada, mas o controlo causal já qualificado com prioridades e banco fixo pediu apenas **797**. Mesmo concedendo duração zero às 254 leituras CPU sem preço no seu sítio, a combinação mais favorável a 10 s, com todas as lacunas de prefill gratuitas, excede o orçamento por **1,283 s**. A escolha ótima com conhecimento do futuro chegava a 414 leituras no decode. O intervalo entre 414 e 918 continua sem política causal demonstrada. [Pré-registo](protocol.md) · [Adenda do preço por sítio](prefill-price.md) · [Recibo](evidence/receipt.json) · [Referência com conhecimento do futuro](../README.md)

| Organização da CPU | 5 tokens | 148 tokens | Prefill | Decode | T2 |
|---|---:|---:|---:|---:|---:|
| Carry C269 com prioridade e banco fixo | 34 | 1 024 | 1 058 | 797 | 1 855 |
| P40-LRU, 25 camadas com 40 lugares e banco fixo | 34 | 1 053 | 1 087 | 1 106 | 2 193 |
| P1000-LRU, partilhando os 1 000 lugares e conservando o banco fixo | 36 | 1 124 | 1 160 | 1 103 | 2 263 |
| U1262-LRU, partilhando primários e as 263 entradas CPU do banco | 34 | 1 014 | 1 048 | 918 | 1 966 |

A unidade é uma leitura completa de expert de 13 219 200 B úteis. Só partilhar os 1 000 lugares manteve quase todo o custo de decode do P40 e aumentou o prefill em 73 leituras. Converter o espaço do banco em backing comum retirou outras 112 e 185 leituras a P1000 no prefill e decode. O controlo C269 e P40-LRU usam políticas de escolha diferentes. As três linhas LRU isolam o efeito da organização física mantendo a mesma regra. [Controlo do mesmo T2](../../replay/README.md)

## Quem podia estar residente antes de T2

A inicialização lê primeiro o segmento PFJ1 de 4 541 088 B que o cliente selou antes do POST. Reconstitui os 1 000 primários CPU, as 263 chaves CPU do banco de vítimas e os 36 membros comuns aos dois conjuntos. O pool unificado começa com 1 227 identidades e 35 entradas livres. A sua arena ocupa 16 686 022 656 B, dentro do orçamento de 16 696 556 544 B para estas matrizes. A coexistência de views de último leitor, buffers em voo e metadados precisa de verificação no runtime.

Dos 7 300 eventos de procura CPU do sufixo T1, tirámos a última ocorrência observada de 1 224 das 1 227 identidades. As três restantes começam empatadas como mais antigas. Durante T2, todos os experts pedidos pela wave ficam protegidos antes de substituir qualquer residente. O desempate usa a identidade (camada,expert) e a promoção segue a primeira ocorrência na wave. Cada braço conserva o estado entre 5, 148 e as 46 avaliações unitárias. O recibo sela a evolução e os estados finais por fase. O mecanismo recebe cada procura quando o router a torna disponível. Com banco inicialmente vazio, materializar as últimas vítimas no sufixo T1 exige 1 530 entradas CPU e 613 entradas provenientes de CUDA, 20,225 e 8,103 GB de payload. O mínimo histórico com estado anterior desconhecido é 1 272 e 518, respetivamente. Este trabalho inicial é comum aos três braços.

| Trabalho do candidato U1262 | Prefill | Decode |
|---|---:|---:|
| Leituras CPU do disco | 651 | 662 |
| Leituras CUDA do disco / do banco | 397 / 69 | 256 / 69 |
| Bytes de disco úteis, ambas as tiers | 13 853 721 600 | 12 135 225 600 |
| Bytes do pack alinhado | 13 856 538 624 | 12 137 693 184 |
| Payload de SET para primários CUDA | 6 160 147 200 | 4 296 240 000 |

U1262 evita as cópias do banco CPU para a arena de P40-LRU, que somam 1 335 139 200 B no prefill e 1 982 880 000 B no decode. Em U, 274 dos 651 READ CPU do prefill e 159 dos 662 do decode servem identidades sem nova reserva de demanda naquele sítio lógico. O pager terá de intercetar estes consumos mesmo que as tags primárias já estejam instaladas. Todos os braços mantêm o mesmo trabalho CUDA. Não há restauro de um estado terminal externo depois da última avaliação.

## Cobertura dos preços e orçamento das leituras novas

O preço tem de corresponder à mesma identidade no mesmo (chamada,tile,camada,wave). No prefill U tem 339 READ CPU com homólogo físico e 312 sem preço; as 397 leituras CUDA têm homólogo. Os READ CPU coincidentes somaram **7,535 / 7,142 segundos de worker** nos dois processos físicos anteriores, e os READ CUDA **7,789 / 7,635**. Essas somas descrevem a FIFO medida para a população antiga, com até quatro leituras em voo. A conversão de volume em parede abaixo usa separadamente os débitos médios observados no pack de 2,522 / 2,628 GB/s. [Preço físico do prefill](../../prefill_frontier/transport/joint/README.md)

| Decode U1262, duas medições anteriores | RP | PR |
|---|---:|---:|
| READ CPU com preço / sem preço | 408 / 254 | 408 / 254 |
| Duração READ coincidente, soma dos workers | 2,997 s | 3,036 s |
| Maior READ conhecido por callback CPU, somado pelos callbacks | 2,323 s | 2,351 s |
| Exterior do decode e cadeias CUDA conservados | 3,908 s | 3,909 s |
| Tempo condicional, com READ novos e instalação de páginas a zero | 6,231 s | 6,260 s |
| Margem até 47/6 s | 1,602 s | 1,573 s |
| Maior preço uniforme admissível por READ CPU novo | 9,628 ms | 9,474 ms |

As 254 leituras sem preço somam **3 357 676 800 B** e afetam 222 callbacks. O cálculo admite até quatro READ simultâneos e cobra, em cada callback, apenas o excesso do maior READ novo sobre a cadeia já cobrada. O limite uniforme assume o mesmo preço para todos os novos e dá custo zero à publicação, ao binding e à sincronização adicionais. Os tetos assim calculados são 7,543 / 7,508 tokens emitidos por segundo, ou 7,382 / 7,348 avaliações por segundo para as 46 chamadas. O tempo efetivo da nova agenda continua desconhecido. [Preços de origem e denominadores](../../replay/decode_clock/README.md)

Com 1 048 leituras de prefill e os quatro cruzamentos das duas travessias de cada fase, o défice para o objetivo conjunto vai de **2,435 a 2,686 s** com as lacunas seriais observadas, **1,643 a 1,894 s** no pipeline otimista e **1,283 a 1,535 s** com lacunas gratuitas. São cenários com débitos do carry anterior e custos do novo pager por medir. A redução condicional no decode do oráculo indica margem para outro seletor causal que demonstre menor trabalho que o carry e preserve esse ganho no mesmo pedido. Este resultado encerra a variante LRU aqui descrita.

## Reprodução

Protocolo `671868a6`, adenda `06805c23`, código congelado `8c95d927`. Cinco testes cobrem empates, pins, ordem de promoção, independência de um sufixo futuro, conservação por tier, limites de preços e recusa de transferir preço entre waves. Dois processos CPU em checkout limpa reproduziram byte a byte os 24 823 B do recibo com SHA-256 `ba87a65b92fa4f16e9b1ec44d4b4321a74f8eb070789a42b7d16e445607a173b`. R01 consumiu 1,10 s de parede e 81 500 KiB de RSS; R02, 0,94 s e 81 280 KiB. A raiz de arquivo fornece as partes 63, 65, 66, 69 e 71. O ensaio fez zero forwards.

```sh
U=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/global_residency/causal
OPENBLAS_NUM_THREADS=1 "$TESY_VENV/bin/python" -IB "$U/test_screen.py"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$TESY_VENV/bin/python" -IB "$U/screen.py" \
  --archive "$ARCHIVE" --new-output-dir "$NEW"
```
