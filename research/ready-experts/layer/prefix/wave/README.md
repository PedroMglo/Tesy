# O ganho da fila chega à conversa e justifica um backend novo?

**NO_GO para financiar um backend dedicado à junção de leituras, ao pipeline de duas tiles e ao banco fixo aqui avaliados no portátil.** Promover um expert na fila adiantou o consumidor de uma wave real. A disposição aprendida em T1 também aproximou mais experts que o segundo turno viria a pedir. A melhor composição ensaiada ainda tem pisos de **12,213 s e 13,165 s** até ao primeiro conteúdo final, dando de graça as cópias dos hits do banco. Estes são limites condicionais sobre dois processos com o mesmo histórico nominal. O melhor resultado efetivamente medido numa conversa continua a ser **17,689 s e 5,357 tok/s no mesmo turno**, com o pack e a fusão CPU. R0 slots40-persistent, ub32 e contexto 8 192 continua como controlo operacional. M3 PARTIAL e M4 NOT_MET. [Medição no cliente](../../../cpu_wave/README.md) · [Decisão de arquitetura](../../../../../docs/architecture/0005-execucao-local-por-perfil.md)

## MEDIDO no portátil, quatro leitores e um consumidor

Na entrada da espera da chamada 2, tile 1, camada CPU1, havia nove hits e sete reservas na fila. Os dois processos históricos confirmam que o consumidor dependia das sete publicações. A espera observada foi 31,153 ms em P97 e 37,410 ms em P106. A fixture leu os registos reais do pack C291 no NVMe interno, instalou gate, down e up nos slots e gerações de C269 e fez o remap das 32 linhas top-4. A barreira medida começa quando os quatro workers podem aceitar trabalho e termina quando o consumidor devolve os IDs físicos. O FFN começa depois. Houve um quarteto de paridade seguido de dois blocos opostos de cinco quartetos. O mutante com geração anterior foi recusado. Nos 44 braços conferimos 308 publicações, 2 112 hashes de matrizes e 5 632 IDs físicos. [Protocolo](protocol.md) · [Relógios dos 44 braços](evidence-20261128-r01/arms.jsonl.gz) · [Comparações emparelhadas](evidence-20261128-r01/physical.json)

| Tratamento | Mediana da barreira, ordem F/P/S/M | Ordem M/S/P/F |
|---|---:|---:|
| F, fila 47, 3, 10, 48, 82, 44, 98 | 34,507 ms | 33,460 ms |
| P, 48 passa para segundo, sete leituras individuais | 33,095 ms | 33,323 ms |
| S, um só worker aceita 47 e 48 e faz duas leituras | 32,854 ms | 33,126 ms |
| M, mesmo worker, leitura única incluindo 36 864 B de padding | 32,520 ms | 34,452 ms |

| Mediana das cinco diferenças da barreira | Ordem direta | Ordem inversa |
|---|---:|---:|
| Ganho de P sobre F | **+1,249 ms** | **+0,403 ms** |
| Ganho de M sobre F | +1,577 ms | −0,992 ms |
| Ganho de M sobre P | +0,397 ms | −1,461 ms |
| Ganho de M sobre S | +0,334 ms | −1,185 ms |

A promoção individual tem **GO_LOCAL** com 5/5 e 3/5 sinais favoráveis, mantendo o drain adiantado em 1,243 e 0,409 ms. A leitura conjunta tem **INCONCLUSIVE**. Comparada com F, fez o par 47/48 ficar disponível 5,951 e 6,682 ms mais tarde. O expert 98 fez a última publicação em todos os braços cronometrados de F, P e M. A ordem de quem recebe o trabalho e a ordem de quem liberta a barreira explicam por que medir só o par daria outra decisão. A promoção é implementável no serviço atual e conserva o seu valor como componente experimental.

## TRACE_DERIVED no pedido nominal com histórico

Selámos 36 caminhos físicos usando só as 5 727 reservas de T1. O processo de construção leu os primeiros 87 736 registos, verificados pelo selo anterior ao segundo POST. P97 e P106 reutilizaram 2 044 posições, avaliaram 153 novas e confirmaram os mesmos 47 IDs. Ambos os relógios incluem os custos exteriores que lhes pertencem. A primeira peça final provém da amostra 45, chamada 46. A duração total do decode prolonga-se até à chamada 48. Cada grupo conserva a sua camada e tile. A disposição nova nunca foi escrita no NVMe. [Seleção antes de T2](layout-protocol.md) · [36 permutações](evidence-20261128-r01/plan.json)

| Disposição | Adjacências antes do primeiro final | Adjacências em todo o decode | Piso até ao primeiro final P97 / P106 | Piso de decode para 47 IDs P97 / P106 |
|---|---:|---:|---:|---:|
| ID crescente do pack | 126 | 6 | 13,969 / 15,102 s | 8,834 / 9,093 s |
| Caminhos escolhidos em T1 | 227 | 52 | 12,265 / 13,399 s | 8,077 / 8,332 s |

A tabela concede zero tempo a todo o grupo que contém qualquer par vizinho, incluindo ambos os intervalos adjacentes. A união conta cada nanossegundo uma vez. Na fila realmente observada, 214 das 227 adjacências treinadas já estavam pendentes quando saiu o primeiro participante, 137 nas quatro primeiras posições e 83 já à cabeça. As 52 adjacências de decode estavam pendentes e 44 já à cabeça. O custo de preparação ou reescrita dos 61,096 GB do pack, o padding extra, as outras conversas e cada custo de sincronização ainda teriam de ser pagos. O resultado fecha estas duas disposições isoladas neste pedido. O antigo teto retrospetivo de 1 371 comandos para uma disposição escolhida com o turno inteiro conserva o seu estatuto de limite. [Regiões e cortes por braço](evidence-20261128-r01/layout.json) · [Relaxação para qualquer disposição linear](../batch-protocol.md)

## Quanto se pode ganhar combinando mecanismos

Na chamada de 148 permitimos que as cinco tiles 32+32+32+32+20 usem dois estágios, camadas 0–24 e 25–35. Cada estágio preserva a ordem das tiles. A chamada de 5 termina antes e o primeiro decode começa depois. C269 aplica o contexto de memória e reutiliza um resultado de grafo em `process_ubatch`. A geometria exige a KV anterior de cada camada, a máscara por tile, a proteção do input de cada grafo e o último consumidor antes da reciclagem dos slots. Dois residuais F32 de 32 × 2 880 ocupam 737 280 B. O pico de workspace de um executor concorrente nos dois dispositivos continua desconhecido. O limite oferece gratuitamente esse espaço e toda a transição ambígua entre os estágios. O antecedente Sarathi-Serve avalia capacidade de serviço em conjuntos de pedidos, incluindo Falcon-180B em oito A100. A pergunta do Tesy incide na latência de uma conversa com uma GPU discreta. [Auditoria do pin e das dependências](../../../../qualification-retake/phase_fd/integrated/tile_pipeline/protocol.md) · [Sarathi-Serve, método e hardware](https://arxiv.org/html/2403.02310v2#S5.SS1)

O pipeline com a disposição treinada e as regiões elegíveis inteiramente grátis dá **11,622 / 12,719 s** até ao primeiro final. Há 16 695 849 600 B úteis de prefill em 51 + 1 212 reservas. Mesmo se o prefill se resumisse a transferir esses bytes e toda a melhoria adicional de decode até exatamente 6 tok/s ocorresse antes da primeira peça, seriam necessários **6,970 / 9,417 GB/s**. O endpoint e a bridge do NVMe anunciam PCIe a 16 GT/s ×4. Conceder 8 GB/s brutos em cada sentido já ignora codificação e pacotes. No relógio integral de P106 isso deixa **314,087 ms**, equivalentes a 2 512 695 224 B ou 191 admissões inteiras por evitar nesta hipótese. Dar gratuitamente os 646,428 ms pré-stream do observador P106 reduz a banda mínima deste braço a 6,901 GB/s. O teto físico isolado deixa então de excluir o alvo. O limite do trabalho por camada continua a excluí-lo. [Composição no mesmo relógio](pipeline-protocol.md) · [Custos por estágio e banda](evidence-20261128-r01/pipeline.json) · [Proveniência do intervalo pré-stream](../../client_cost.py)

O banco de 353 experts, selado antes da mensagem, ocupa 4 666 377 600 B de payload adicional. Em T2 cobre 155 leituras de prefill (2 048 976 000 B), 171 no decode antes do primeiro final e uma na cauda. Ao retirar os hits da fonte NVMe, as adjacências físicas treinadas baixam de 175 para 139 no prefill e de 52 para 34 no decode. Demos aos pares frios latência de READ zero, conservámos os bytes deles no PCIe e os preços de READ dos experts frios isolados. Cobrámos o maior job e a divisão do serviço pelos quatro workers. O banco fica fixo durante T2. Uma política que o renove altera a ordem das expulsões quando as tiles se intercalam. [Protocolo do banco](bank-protocol.md) · [Preços e populações](evidence-20261128-r01/bank.json)

| Piso condicional, SET pago, duas tiles, ligação até 8 GB/s | Primeiro final P97 / P106 | Decode de 47 IDs P97 / P106 |
|---|---:|---:|
| Banco vazio, ordem numérica | 14,941 / 16,014 s | 8,890 / 9,166 s |
| Banco vazio, ordem treinada | 13,961 / 15,026 s | 8,488 / 8,749 s |
| Banco T1, ordem numérica | 12,772 / 13,701 s | 7,944 / 8,161 s |
| Banco T1, ordem treinada | **12,297 / 13,255 s** | **7,651 / 7,884 s** |
| Banco T1, ordem treinada, SET dos hits grátis | **12,213 / 13,165 s** | **7,595 / 7,823 s** |

Oferecer até a cópia dos hits deixa margem de apenas 10,192 ms no decode de P106 para 6 tok/s e faltam 3,165 s no primeiro final. Com o crédito pré-stream integral ainda faltam **2,518 s** nesse braço. O teto dos dois programas depende da estabilidade dos restantes preços de camada. Uma redução do serviço das faltas isoladas, uma origem já pronta antes da procura ou menos passos seriais confirmados pelo target pode mudar esse parecer. O próximo discriminante é aplicar uma seleção renovável às duas tiles, verificando a propriedade de cada vítima e os bytes que ainda chegam tarde. Para justificar outro executor será preciso demonstrar depois que a fronteira do atual impede entregar os bytes ou as ativações a tempo. O caso de código, a sessão sustentada e a promoção operacional da nova combinação ficam NOT_RUN. O ganho local fica disponível para uma experiência composta com controlos contemporâneos.

## Proveniência e reprodução

O R0, C317 e C318 mantêm-se fechados. Foram reproduzidos os oito tamanhos e SHA-256 C317 e as contas C318 de oito braços. Os cortes históricos na via de +15% continuam 17,62% nominal e 18,02% código no decode do candidato. A continuação de worker em C317 conserva INCONCLUSIVE quanto ao caminho crítico. Estes cortes pertencem a um avaliador diferente desta decisão nominal de arquitetura. [Reanálise consolidada](../../../../post-c320/README.md)

A fixture física usou o NVMe interno, os pesos reais dos experts e os SET CPU de C269. Pediu 4 072 747 008 B nos braços e 4 191 744 000 B incluindo inicialização. O contador de todo o NVMe avançou 7 954 584 setores de 512 B durante os braços. O scope chegou a 350 007 296 B, com zero swap. Demorou 67,496 s incluindo a janela interna de 60 s, em AC/performance. Em 64 amostras os máximos foram 69,125 °C na CPU, 42,14 °C na GPU e 35,85 °C no NVMe. A RTX 4060 estava visível. Foram zero forwards do modelo completo e zero operações de cálculo na GPU. A energia total é desconhecida. Os quatro processos de análise duraram 0,51, 2,34, 1,15 e 1,27 s e ficaram abaixo de 69 000 KiB de RSS cada. O arquivo novo preserva 15 ficheiros e 517 742 B, além do manifesto. Os PFJ integrais, as respostas e os pesos ficam no portátil. A revisão pública reconstitui as uniões, os estágios, as fontes exclusivas e todos os contrastes a partir dos dados compactos, sem modelo. [Commits, árvores, recursos e hashes](evidence-20261128-r01/provenance.json) · [Comandos físicos e de análise](evidence-20261128-r01/commands.json) · [Manifesto do arquivo](evidence-20261128-r01/archive.json)

Validação de 28 de novembro, com 434 testes de repositório e 42 testes de gates sem modelo. O teste HTTP de inventário precisava de loopback e passou no anfitrião. A revisão com os dois PFJ, o manifesto do pack e o arquivo privado reproduziu a decisão pública. A consolidação conferiu os 45 heads históricos. [Testes de regressão desta unidade](../../../../../tests/test_ready_wave_service.py)

~~~sh
s=research/ready-experts/layer/prefix/wave
python3 -IB "$s/review.py"
python3 -IB "$s/review.py" --raw-archive "$TESY_QUEUE_ARCHIVE" \
  --trace-archive "$TESY_QUALIFICATION_ARCHIVE" --derived-pack "$TESY_PACK_MANIFEST_DIR"
pytest -q tests/test_ready_wave_service.py
~~~
