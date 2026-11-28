# Decisão de backend no portátil após medir quem desbloqueia o prefill

**NO_GO para financiar uma reescrita integral com este mecanismo. GO para conservar a entrega de pesos a partir da primeira leitura obrigatória como componente experimental.** Em oito processos no GPT-OSS-120B MXFP4 original, o executor atual do Tesy conseguiu usar o mesmo registo em RAM depois de o primário ter mudado de dono. Na chamada real de 148 tokens, com 69 chaves conhecidas de antemão, o ganho foi de **462,516 e 233,772 ms** contra o executor contemporâneo e de **522,024 e 191,300 ms** contra a ablação com a mesma RAM. Incluindo o trabalho desde a preparação do histórico, os quatro contrastes continuaram favoráveis. Com 353 janelas escolhidas em tempo real pela frequência das faltas, o melhor piso de primeiro conteúdo final foi **13,146 / 13,300 s**. As duas seleções cobriram 70 leituras de prefill cada e tiveram **zero em comum**. [Preço físico](evidence-20261128-r01/physical-grade.json) · [Limites das políticas](evidence-20261128-r01/causal-grade.json) · [Gerações em comum](evidence-20261128-r01/overlap.json)

O melhor pedido HTTP nominal já medido continua a combinar **17,689 s até ao primeiro conteúdo final, 17,938 s até à conclusão válida e 5,357 tok/s**. Para o objetivo do cliente faltam 7,689 s e 0,643 tok/s nesse pedido. A unidade atual usou um cliente numérico e duas observações históricas da mesma conversa. HTTP com esta intervenção, proteção do caso de código e sessão sustentada permanecem NOT_RUN. R0 slots40-persistent continua o controlo operacional, M3 PARTIAL e M4 NOT_MET. [Pedido HTTP e validação funcional](../../../../../cpu_wave/README.md)

## Quem esperava pelos bytes

**TRACE_DERIVED.** Na chamada de 148 de cada journal C281 há 1 212 reservas, 3 636 SET e 1 296 barreiras de consumo. O expert 54 entrava na camada CPU 14 no slot 16, geração 3. A primeira tile cedeu o slot a 118, geração 4. Na quinta tile, a segunda wave precisou de 54 no slot 14, geração 7. O instante do último pin de 54 anterior ao segundo turno é desconhecido. Com os restantes pesos nos instantes observados, tornar só este expert disponível na reserva podia adiantar um consumidor em 5,557 ms (P97) ou 5,126 ms (P106). Para as 75 recargas da coorte anterior, o máximo condicionado foi 95,747 e 96,690 ms em 16 barreiras disjuntas. Libertar instantaneamente todas as 1 212 reservas daria 5,574 e 5,560 s no mesmo cálculo. Esses números mantêm as restantes horas fixas e pertencem a cada journal. [Protocolo do replay](protocol.md) · [Barreiras e conservação](evidence-20261128-r01/wait-grade.json)

**MEDIDO no portátil.** O worker enviou a primeira leitura obrigatória diretamente para uma janela RAM alinhada. Os três SET originais copiaram os mesmos bytes para os slots CPU ou CUDA. O worker pôde imediatamente servir outra falta com o seu staging privado. A janela reteve os bytes até ao retorno sincronizado dos 148 tokens, inclusive depois de o primário ter mudado de dono. R usou sempre o NVMe. O alocou e preencheu as mesmas janelas que H e voltou a ler do NVMe durante os 148 tokens. H usou as janelas nas 70 faltas selecionadas. O controlo operacional permanece R0 slots40-persistent. O comparador R da fixture acrescenta ao pack C291 a fusão CPU anteriormente qualificada e a mesma observação nos três braços. [Código do percurso dos dados](delivery.cpp.in) · [Interface do executor e libertação](client.cpp.in)

A coorte conhecida de antemão tem 69 chaves, 44 CPU e 25 CUDA, e ocupa **912 310 272 B** fora dos primários. Uma chave foi pedida duas vezes. O e H aproveitaram os mesmos pedidos do descritor desde a ativação da instrumentação no modelo já carregado até à entrada nos 148 tokens, com 6 039 leituras de preparação em todos os braços. Ao servir a segunda chamada, H passou de 1 212 para 1 142 leituras de 13 221 888 B no descritor. A diferença medida é **925 532 160 B**. Cada hit ainda paga as três cópias para o destino. A escrita nas janelas e a libertação entram nos relógios de custo aplicáveis. Bytes físicos da NAND e energia total do portátil permanecem desconhecidos.

O processo V comparou as 207 matrizes com SHA-256 independente, as 69 janelas completas com o pack e os conteúdos com os primários. As verificações custaram mais 912 310 272 B de leitura no descritor só em V. Nos oito processos coincidiram os 78 IDs do primeiro turno, os 47 do segundo até EOG, as 47 linhas completas de 201 088 logits F32 finitos, as rotas de decode, quatro cortes serializados de KV e a propriedade dos primários após o prefill e o primeiro decode. No site observado coincidiram as 13 reservas, as cinco listas de pins e os 400 índices físicos de remap dos 20 tokens. Quatro workers reais fizeram o serviço. O contrato de paridade cobre aquela trajetória e as vistas registadas. A observação de tensores independentes de atenção ou máscara e a paridade da distribuição de sampling ficam fora desse contrato. [Protocolo físico e ordem dos braços](provider.md) · [Verificador sem modelo](run.py)

## Tempos de cada processo

Os primeiros dois processos qualificam a identidade. Os restantes medem o custo nas ordens R–O–H e H–O–R. O tempo de CPU14 começa na primeira wave e termina ao regressar o remap da segunda. A coluna de 148 inclui armar o mecanismo, a chamada, sincronizar e libertar as páginas. O último relógio começa antes de reservar a RAM no cliente numérico, com o modelo já carregado, e termina nessa mesma libertação. As 46 chamadas seguintes serviram para verificar exatidão. O processo V paga a leitura diagnóstica e fica fora dos pares.

| Braço | CPU14, ms | Segunda wave, ms | Último expert dessa wave | Chamada de 5, s | 148 com cleanup, s | Dos preparativos ao fim de 148, s |
|---|---:|---:|---:|---:|---:|---:|
| ref (R) | 69,178 | 35,619 | 54 | 0,444 | 8,770 | 81,304 |
| parity (V) | 61,914 | 29,536 | 107 | 0,443 | 11,176 | 83,842 |
| r1 (R) | 56,126 | 30,882 | 54 | 0,444 | 8,827 | 81,883 |
| o1 (O) | 62,548 | 31,974 | 54 | 0,442 | 8,886 | 81,706 |
| h1 (H) | 60,353 | 30,459 | 107 | 0,441 | 8,364 | 81,016 |
| h2 (H) | 49,715 | 23,599 | 107 | 0,441 | 8,598 | 81,177 |
| o2 (O) | 67,789 | 37,204 | 54 | 0,445 | 8,789 | 81,710 |
| r2 (R) | 68,424 | 35,286 | 54 | 0,447 | 8,832 | 82,488 |

Diferenças H menos o comparador, em milissegundos. Valores negativos são ganhos do reuso.

| Relógio | H1−O1 | H1−R1 | H2−O2 | H2−R2 | Decisão pré-registada |
|---|---:|---:|---:|---:|---|
| CPU14, duas waves | -2,195 | 4,227 | -18,074 | -18,709 | INCONCLUSIVE |
| Só a segunda wave | -1,515 | -0,423 | -13,605 | -11,688 | GO_NEXT_STAGE |
| Chamada de 148 e cleanup | -522,024 | -462,516 | -191,300 | -233,772 | GO_NEXT_STAGE |
| Preparação, T1, 5 e 148 | -690,467 | -867,259 | -532,714 | -1310,302 | GO_NEXT_STAGE |

A intervenção alterou o último produtor. Nos quatro braços de preço R/O, a leitura do expert 54 durou 15,831–17,841 ms e ele publicou os últimos bytes de que a segunda wave precisava. Em H1 e H2, a sua leitura foi satisfeita no banco e a última publicação passou para o expert 107. A wave encurtou nos quatro contrastes. Contando também desde a primeira wave, H1 perdeu 4,227 ms face a R1 e H2 ganhou 18,709 ms face a R2. A dispersão destes dois pares limita a atribuição local. O ganho dos 148 tokens inclui as restantes camadas e os efeitos entre os quatro workers. [Tempos e identidades dos produtores nos oito processos](evidence-20261128-r01/arms.json.gz)

Medi também o caminho do expert 107, que continuou a vir do NVMe em todos os processos. A partir da entrada na primeira wave, o READ começou a 33,330 / 41,136 / 43,347 ms em R1 / O1 / H1. Durou 19,981 / 17,777 / 16,320 ms. O serviço de disco mais curto em H1 foi insuficiente para compensar o início mais tardio. Na ordem inversa, o READ começou a 34,287 / 44,045 / 44,515 ms em H2 / O2 / R2 e durou 14,721 / 20,843 / 21,074 ms. Aí H2 publicou 107 antes dos dois controlos. Estes números usam a entrada no pread do worker e a publicação da geração válida, ambas registadas no relógio do cliente numérico. A identidade do último produtor e o tempo da sua leitura, por si só, não determinam a hora do regresso ao consumidor. [Treze aquisições e respetivos três SET em cada braço](evidence-20261128-r01/arms.json.gz)

## O que se consegue escolher durante uma conversa

O replay começa com o banco vazio antes da primeira reserva do primeiro turno. Num retorno drenado, a política escolhe por frequência das faltas anteriores ou pela última falta. Uma eleição apenas autoriza a próxima leitura obrigatória a preencher a janela. Só a partir da publicação essa janela pode servir outro pedido. O primário conserva os 40 slots e o target conserva a ordem. O ensaio de 69 janelas usa a capacidade da fixture e o de 353 confronta a hipótese com 4 667 326 464 B de memória adicional. Ambos os segundos turnos são réplicas do mesmo histórico. P106 observou o primeiro turno até ao corte selado. Para P97, o estado secundário à entrada é transferido desse prefixo depois de verificar a correspondência do primário, das reservas e da trajetória. [Protocolo](causal.md) · [Código e controlos](causal.py)

São **pisos TRACE_DERIVED**, em segundos. As colunas «SET pagos» retêm o cliente integral e o grafo observado. As colunas «favorável» concedem os SET nos hits, a coordenação, os intervalos das 711 waves vazias elegíveis e, apenas para o primeiro conteúdo de P106, mais 0,646 s do cliente. Os dois relógios usam o mesmo trabalho e sobrepõem-se durante parte do decode.

| Seleção | Hits T2 / 2 354 P97 e P106 | Primeiro final, SET pagos P97 / P106 | Decode de 47 IDs, SET pagos P97 / P106 | Primeiro final favorável P97 / P106 | Decode favorável P97 / P106 |
|---|---:|---:|---:|---:|---:|
| Reuso desligado | 0 / 0 | 14,197 / 15,097 | 7,358 / 7,466 | 13,580 / 13,720 | 7,358 / 7,466 |
| Recência 69 | 3 / 3 | 14,182 / 15,081 | 7,358 / 7,466 | 13,563 / 13,704 | 7,358 / 7,466 |
| Frequência 69 | 20 / 20 | 14,146 / 15,045 | 7,344 / 7,450 | 13,523 / 13,663 | 7,343 / 7,449 |
| Recência 353 | 12 / 12 | 14,148 / 15,047 | 7,356 / 7,463 | 13,527 / 13,668 | 7,356 / 7,463 |
| Frequência 353 | 140 / 140 | 13,791 / 14,713 | 7,226 / 7,340 | 13,146 / 13,300 | 7,223 / 7,337 |

No braço causal de 353 janelas, 128 estavam preenchidas no fim do primeiro turno. Houve 1 hit na chamada de 5, 70 na de 148, 68 nas chamadas de decode até ao primeiro conteúdo e 1 na cauda. Com a capacidade física de 69 janelas, só 14 estavam preenchidas e houve 9 hits nos 148 tokens. Em ambos os casos o expert 54 faltava. A comparação com recência mede o valor da escolha com a mesma memória. O limite mais favorável de frequência 353 ainda excede o prazo por **3,146 / 3,300 s**. Para este mesmo braço, pagando todos os SET e o cliente integral e concedendo o avanço de CPU, uma redução uniforme do tempo dos READ restantes teria de atingir **30,0989% em P97 e 39,2291% em P106**. A unidade é duração de serviço das leituras que falham a cache. Os contadores do NVMe e a taxa do cliente são grandezas diferentes. [Margens, fases e ponto de equilíbrio por journal](evidence-20261128-r01/causal-grade.json)

**Auditoria posterior de identidade e tempo.** As 70 faltas causais de frequência 353 e as 70 físicas têm zero interseções na chamada de 148, incluindo a ocorrência que repete um expert. Ao oferecer a publicação na reserva com os restantes produtores nas horas observadas, a coorte física poderia adiantar 16 esperas em ambos os journals, com soma **86,959 / 85,393 ms**. As 70 causais poderiam adiantar 10 / 9 esperas, com **42,945 / 32,615 ms**. As nove da capacidade 69 adiantariam 2 / 1, com **7,372 / 3,556 ms**. O cálculo pressupõe que o serviço dos outros jobs fica fixo. O hardware pode acelerar outros produtores quando se retira pressão ao NVMe. As diferenças entre a soma condicionada e o tempo de uma execução nova não identificam esse efeito. [Auditoria e protocolo](cohort-audit.md) · [Recibo das barreiras](evidence-20261128-r01/overlap.json)

**Condição de reabertura.** Para testar se vale a pena levar o componente ao cliente, o próximo discriminante é identificar se o tempo ganho inclui a entrega mais cedo dos pesos que continuaram a vir do disco. Medir nos mesmos quatro workers a reserva, o despacho, o fim do READ, os três SET e a publicação dessas gerações no último consumidor, com neutralidade OFF/ON da instrumentação. Uma ablação pode manter a janela pronta e reter o despacho até à hora da referência. Os dois sinais distinguirão o custo da própria leitura da contenção que ela impunha aos outros. Só uma dependência com margem no pedido e uma limitação demonstrada da interface atual reabre o investimento num executor completo. Os dois pares físicos justificam conservar o protótipo para combinações que tenham uma origem causal dos pesos e uma medição conjunta.

## Recursos e reprodução

No Ryzen AI 9 HX 370 e RTX 4060 Laptop, o GGUF e o pack estavam no NVMe interno Btrfs, em AC e perfil performance, com o driver 620.73.04 e contexto 8 192. A campanha ocupou **1 249,875 s** incluindo as oito admissões individuais e 756,040 s em execução dos processos do modelo. Picos de 17 266 372 608 B no cgroup, 6 848 MiB de VRAM e zero swap. Máximos de 95,375 °C na CPU, 65,00 °C na GPU e 57,85 °C no NVMe. A integração de potência da GPU estima 11,025 kJ. O arquivo privado exclusivo tem 198 ficheiros, 13 566 108 B e 24 referências de providers registadas sem seguir os links. [Host, comandos, versões e orçamento](evidence-20261128-r01/provenance.json) · [Selo do arquivo](evidence-20261128-r01/archive.json)

A execução física ficou congelada em `083c2336`, o replay causal em `3c0ef14e`. O replay levou 6,41 s e atingiu 177 428 KiB de RSS. A auditoria de gerações em `2fef81eb` levou 3,86 s e 155 324 KiB. O SHA-256 das 1 212 identidades ordenadas comprimidas é `98fef0d8eba7974e122a49ce789484a04442ea8153430dbdc590ae23ec3376cc`. Os testes de origem, geração, parking, remap e admissão causal funcionam sem modelo. A alteração de formatação posterior à campanha reproduz byte a byte o C++ compilado, SHA-256 `4d56179a86c147b4c22164c1f8530b73a801fa68d00be260377714d2c035f577`.

```sh
u=research/ready-experts/verifier_wait/forecast/retention/eviction/late_owner
e="$u/evidence-20261128-r01"
python3 -IB "$u/observe.py" --check "$e"
python3 -IB "$u/run.py" check "$e"
python3 -IB "$u/causal.py" check "$e"
python3 -IB "$u/compare_cohorts.py" "$e"
python3 -IB -m unittest discover -s "$u"
python3 -IB research/post-c320/analyse.py --raw-dir "$TESY_C317_RAW"
python3 -IB research/consolidacao-20261123/verify.py
```

A reconstrução do último recibo a partir dos journals aceita `--archive "$TESY_QUALIFICATION_ARCHIVE" --new-output-dir "$NEW_DIR"` depois do argumento de evidência de `compare_cohorts.py`. Neste portátil, os oito raw C317 passaram tamanho e SHA-256. A consolidação em clone completo verificou 45 heads e 7 533 versões históricas. Os testes locais da unidade passaram em 5 fixtures, além de 444 testes do projeto e 42 dos gates operacionais.
