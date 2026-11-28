# Quanto ganha o cliente com outro backend de experts?

**NO_GO para financiar uma reescrita integral neste perfil.** O backend atual consumiu pesos parciais e reproduziu a camada completa bit a bit. As duas variantes fizeram trabalho útil durante a leitura e perderam para o controlo que já executa os três experts residentes. Um segundo ensaio encontrou um ganho de transporte aproveitável num par real do prefill. No decode o ganho mudou de sinal. Conservar a junção como candidata de prefill e o pack com fusão CPU como componente já medido na conversa. A receita operacional continua em R0 slots40-persistent, M3 PARTIAL e M4 NOT_MET. [Decisão de arquitetura](../../../../docs/architecture/0005-execucao-local-por-perfil.md) · [Medições anteriores no cliente](../../cpu_wave/README.md)

## MEDIDO no FFN completo do portátil

Na primeira posição incremental da captura C270 (posição 189, camada CPU0), o router selecionou 28, 24, 8 e 16. Só o expert 24 faltava. Repusemos essa falta no slot 14 antes de cada braço. O relógio começa na emissão do pedido e termina após o down, a soma das quatro contribuições pela ordem do target e o drain desse pedido. FULL espera pela leitura e calcula os quatro ranks juntos. READY calcula os três residentes durante uma única leitura contígua do quarto. As variantes E32 e EALL usam a mesma biblioteca GGML, com as projeções, biases, SwiGLU, quantização da ativação para down, peso do router e redução do target. E32 entrega 32 linhas ao worker. EALL entrega todas as linhas de gate e up à equipa principal e lê down enquanto ela calcula. As ablações L32 e LALL usam exatamente as respetivas janelas e grafos e só autorizam o primeiro cálculo após a entrega completa. [Protocolo e recursos](protocol.md) · [Implementação](native.cpp)

| Candidato e referência | Ganho emparelhado da camada, ordem direta | Ordem inversa |
|---|---:|---:|
| E32 contra a sua ablação L32 | +0,070 ms | +0,007 ms |
| E32 contra FULL | −0,629 ms | −0,668 ms |
| E32 contra READY | **−1,158 ms** | **−1,319 ms** |
| EALL contra a sua ablação LALL | +0,317 ms | +0,145 ms |
| EALL contra FULL | −0,523 ms | −0,527 ms |
| EALL contra READY | **−0,956 ms** | **−1,178 ms** |

Cada célula é a mediana de cinco diferenças no mesmo sexteto. Nos dez braços de custo de cada candidato, todo o intervalo host de execução do primeiro consumidor coincidiu com leituras de cauda. As medianas dessa interseção foram 27/34 µs em E32 e 167/162 µs em EALL. Reunir as 2 880 ativações F32 antes do down e servir o mesmo peso por várias leituras tem custo. A experiência identifica o débito líquido contra READY; atribuir cada microssegundo à syscall, ao controlador ou ao GGML exigiria outra observação. Os dois candidatos têm **NO_GO_LOCAL** neste estado de residência. [Todos os 66 braços e relógios](evidence-20261128-r01/consumer-arms.json.gz) · [Diferenças por par e contagens](evidence-20261128-r01/decision.json)

Os seis braços de paridade precederam os 60 cronometrados. Conferimos 760 320 palavras F32 de contribuições e 190 080 de FFN contra a referência independente. Nas 44 operações divididas conferimos também 1 013 760 palavras dos oito estágios do expert frio e a ativação efetivamente entregue ao down. A troca de ranks no mutante alterou 720/2 880 saídas. Uma falha injetada após a publicação parcial impediu a publicação final e o consumo por down. O contrato cobre este operador, a rota real e os seus pesos. Os logits do modelo completo, o KV e a distribuição de sampling pertencem a outros ensaios. [Referência C270](../../../qualification-retake/igpu_resident_rank/projection/rank_cpu/README.md) · [Verificador](grade.py)

## TRACE_DERIVED nos dois pedidos nominal153

Reabrimos P97 e P106, dois processos trace-ON do mesmo pedido com histórico. Em cada um o target reutilizou 2 044 IDs, avaliou 153 e gerou 47. Os 2 987 callbacks e as 2 354 reservas reconciliam em cada journal. Oferecemos custo zero a cada grupo selecionado e aos intervalos até às notificações dos vizinhos. Mantivemos fixos os custos exteriores, a geometria, o corte do primeiro conteúdo final e o estado transmitido. Intervalos sobrepostos recebem crédito uma única vez. Esta concessão inclui trabalho alheio ao FFN e dá um piso condicional. [Regra de atribuição](reach-protocol.md) · [Recibo por braço e fase](evidence-20261128-r01/reach.json)

| Regiões oferecidas gratuitamente | Primeiro final P97 / P106 | Decode P97 / P106, 47 tokens |
|---|---:|---:|
| Controlo trace-ON | 18,326 / 19,529 s | 8,947 / 9,214 s |
| Decode CPU com uma falta e fronteiras drenadas | **15,102 / 16,207 s** | 5,644 / 5,810 s |
| Todas as regiões CPU do decode | **11,839 / 12,809 s** | 2,308 / 2,319 s |
| Todas as regiões CPU do prefill | **11,198 / 12,114 s** | 8,947 / 9,214 s |
| Todas as regiões CPU de ambas as fases | 4,711 / 5,394 s | 2,308 / 2,319 s |

Existem 358 regiões de uma falta antes do primeiro final e outras nove no restante decode, em cada processo. A combinação de ganhos nas duas fases é uma hipótese legítima. Mesmo sobre a união generosa de todas as regiões CPU, cumprir os 10 s exigiria retirar **61,15% / 67,41%** do seu tempo até ao primeiro final, mantendo o resto fixo. O preço alvo de decode é 47/6 s. Estes números orientam a escolha de arquitetura. O efeito no cliente continua a exigir um pedido trace-OFF com R0 contemporâneo, ablação, proteção de código e sessão sustentada. [Controlo natural já medido no portátil](../../cpu_wave/README.md)

## MEDIDO para uma alternativa comum ao prefill e ao decode

Um layout pode colocar lado a lado experts frequentemente pedidos juntos e emitir uma leitura para os dois destinos. A exatidão exige o mesmo payload. O limite concede ao layout os IDs do turno inteiro. Mesmo permitindo uma escolha separada por relógio, cada expert só tem dois vizinhos num pack linear. Até ao primeiro final o teto é 1 371 comandos eliminados de 2 330 reservas e no decode é 309 de 1 091. A ordem numérica existente oferece apenas 126 e seis adjacências, respetivamente. Incluímos preloads e concedemos disponibilidade simultânea a todo o grupo para o limite. Assim, mesmo com a melhor disposição, os primeiros finais exigiriam **6,073 / 6,950 ms de parede por comando eliminado** em P97/P106, em média. Nos decodes seriam **3,603 / 4,468 ms**. [Prova de incidência e cobertura](batch-protocol.md) · [Certificados por fase](evidence-20261128-r01/batch.json)

Selecionámos sem usar os tempos o primeiro par já adjacente na mesma wave de reservas na chamada de 148 e no decode anterior ao primeiro final. Ambos os journals apontaram os mesmos slots e gerações. No portátil, D usa dois leitores concorrentes, S duas leituras em série no mesmo worker e M uma leitura vetorizada com os mesmos dois destinos e mais 36 864 B de padding. Os quatro workers participam em todos os braços. O intervalo mede até os dois registos estarem disponíveis e a equipa ter terminado o pedido. Cada paridade e cada braço cronometrado passaram nos seis hashes das matrizes. [Protocolo físico](pair-protocol.md) · [42 braços, relógios e bytes](evidence-20261128-r01/pair-arms.jsonl.gz)

| Par medido | M contra D, ordens direta / inversa | M contra S | Decisão de componente no par |
|---|---:|---:|---|
| Prefill, chamada 2, tile 1, CPU1, experts 47/48 | **+2,374 / +0,526 ms** | +0,462 / +0,575 ms | GO local |
| Decode, chamada 9, camada 34, experts 106/107 | **+0,694 / −2,049 ms** | +0,444 / −1,907 ms | INCONCLUSIVE |

São três diferenças emparelhadas por célula e ordem. Nenhum dos dois pares atingiu o preço médio que a hipótese isolada exigiria. A amostra também não mede os preços de todos os pares de outro layout. O pequeno ganho do prefill justifica guardá-lo para composição. A proteção de decode impede adoção geral. A condição para integrar é obter ganho líquido com as outras procuras da wave a competir pelos quatro workers, respeitar a FIFO ou cobrar a mudança de ordem e conservar o benefício no cliente. [Resumo, seleção e proveniência](evidence-20261128-r01/decision.json)

## Alcance, falhas e reprodução

O antecedente técnico é PagedMoE, que inicia experts disponíveis enquanto lê os restantes e funde reconstrução em bitplanes com GEMV. Os seus testes usam outros modelos e precisões, Ryzen 9950X, RTX 5090, 64 GB e SSD PCIe 5.0. Aqui conservámos o GPT-OSS-120B MXFP4, a aritmética GGML e o pack do perfil HX 370. O resultado sustenta uma decisão de engenharia neste perfil. A possibilidade de um backend diferente reduzir simultaneamente os bytes críticos, o custo de prefill e os passos confirmados continua aberta. [Método e máquinas dos autores, §§7–8](https://arxiv.org/html/2611.03173v1) · [Antecedentes e limitações](../../../post-c320/literatura.md)

A compilação usou as bibliotecas CPU e base de C269 e o compilador fixados pelo recibo. O operador pediu 925 782 016 B ao pack, chegou a 112 615 424 B no cgroup e demorou 0,646 s no filho e 61,430 s incluindo o inventário. Os tempos do segundo ensaio foram 62,205 s incluindo o inventário e 97 251 328 B de pico. Pediu 1 111 154 688 B ao pack. O contador de todo o NVMe avançou 2 170 224 setores de 512 B nessa janela. O máximo observado durante as amostras da camada foi 48,375 °C na CPU, 41,0 °C na GPU e 35,85 °C no NVMe, com duas amostras de runtime e 61 no preflight. Energia total desconhecida. Ambos os ensaios usaram AC/performance, zero swap no scope, zero forwards do modelo completo e zero cálculo GPU. A RTX estava visível com 8 188 MiB. [Comandos de cada identidade](evidence-20261128-r01/commands.json) · [Manifesto de arquivo privado](evidence-20261128-r01/archive.json)

A primeira execução da análise de alcance exigiu por engano um callback da camada 35 mesmo nas tiles sem saída. Parou antes dos resultados. A segunda empregou a máscara já validada do target e preservou a falha original. A unidade mantém os oito ficheiros C317, C318 e as baselines encerradas como referências independentes. A validação pública usa apenas os relógios, contadores e hashes compactos. No portátil, os argumentos adicionais reabrem os raws selados e os dois PFJ. [Implementação da revisão](review.py)

~~~sh
python3 -IB research/ready-experts/layer/prefix/review.py
python3 -IB research/ready-experts/layer/prefix/review.py \
  --raw-archive "$TESY_COMPLETE_FFN_ARCHIVE" --trace-archive "$TESY_QUALIFICATION_ARCHIVE"
pytest -q tests/test_ready_prefix.py
~~~
