# Quanto vale manter os pesos na RAM durante uma conversa?

**Decisão no HX 370 após cobrar a residência da call de 148.** O planeador identifica dez releituras CPU evitáveis com o preload e os mesmos 1 252 frames. No relógio do primeiro conteúdo representam 8,419–19,060 ms projetados. A entrega dos pesos reproduziu-se no NVMe. Mantém-se o backend e o controlo R0. [Estados, braços físicos, caso de código e decisão](partition/shadow.md)

No NVMe interno medimos depois as 1 519 leituras obrigatórias que sobram. Todas já são pedidas na primeira remap da própria camada. O cenário que permite receber o último byte à entrada do router seguinte continua acima dos 10 s nos quatro cortes. [Transporte e banda admissível](transport.md) · [Fronteira da camada](layer-release.md) · [Cobertura que reabriria a decisão](advance.md)

**NO_GO para substituir o backend com base na retenção CPU isolada.** Na agenda dos quatro workers, servir diretamente os 484 acertos adiantaria o primeiro conteúdo final em 1,253 s e 1,276 s. Mesmo dando ao escalonador liberdade de escolher os workers e oferecer toda a antecipação anterior ao callback, os primeiros finais continuariam em pelo menos **15,025 s e 16,315 s** aos preços observados das faltas. A meta é 10 s. O cenário favorável ainda fica abaixo de 6 tok/s nos dois processos. O melhor pedido nominal já medido na configuração pack + fusão CPU continua nos **17,689 s e 5,357 tok/s**. R0 slots40-persistent é o controlo. M3 PARTIAL, M4 NOT_MET. [Pedido medido](../cpu_wave/README.md) · [Protocolo](protocol.md) · [Decisão em nanossegundos](evidence-20261128-r03/decision.json)

| Agenda e serviço | P97 primeiro final, s | P97 decode, tok/s | P106 primeiro final, s | P106 decode, tok/s |
|---|---:|---:|---:|---:|
| DISK observado, reproduzido ponto a ponto | 18,326 | 5,253 | 19,529 | 5,101 |
| Mesmos acertos, cópia com staging gratuito | 17,158 | 5,759 | 18,348 | 5,559 |
| Mesmos acertos, acesso direto gratuito | 17,072 | 5,812 | 18,253 | 5,612 |
| Relaxação livre, acesso direto gratuito nesses acertos | 15,025 | 5,856 | 16,315 | 5,643 |
| Relaxação, serviço CPU inteiro gratuito | 9,148 | 11,165 | 10,433 | 10,399 |
| Relaxação, serviço CUDA inteiro gratuito | 13,220 | 6,744 | 14,438 | 6,499 |
| Relaxação, serviço de ambos gratuito | 5,941 | 20,483 | 7,190 | 18,175 |

**O que pagou o pedido.** Sob a agenda observada, os créditos de acesso direto em P97/P106 foram 51/50 ms no prefill de 5, 349/392 ms no de 148, 853/834 ms até à amostra final e 7/5 ms na cauda. Chegar à resposta validada custaria 17,310/18,513 s. Preservámos a preparação exterior, os intervalos entre chamadas e o tempo de entrega. O prazo de primeiro final acaba após a chamada 46. O relógio de decode do servidor usa 47 IDs e inclui a cauda. A terminação do servidor ocorre depois da validação. Os quatro workers saíram e o journal fechou 52,222/51,122 ms após o último retorno. O cálculo mantém esse cleanup no âmbito original. [Recibos do cliente e proveniência](evidence-20261128-r03/provenance.json)

**Por que a conclusão sobrevive a outro escalonamento.** Das 2 354 gerações (1 594 CPU e 760 CUDA), 1 918 foram reservadas e exigidas no mesmo callback. A cache poupa serviço em 399 dessas gerações. Para cada callback a relaxação cobra só o maior preço individual das restantes e um quarto da soma, usando o maior dos dois. Oferece todo o serviço das outras gerações e sobreposição da preparação com as leituras, conserva a aritmética e os intervalos exteriores. A soma usa callbacks disjuntos. Mesmo nessa relaxação, os preços READ+SET dos pares obrigatórios teriam de cair para **44,7718% / 30,8695%** dos valores de cada processo, se a redução fosse uniforme. Em P106, baixar só os preços CPU a zero, ou só os CUDA a zero mantendo os acertos CPU, ainda falha. Esta última restrição é condicional à geometria, reservas e custos exteriores observados. [Implementação do limite](replay.py)

**Conservação e incerteza.** O controlo reconstruiu exatamente 40 960/40 942 marcos, 2 987 barreiras por processo, 10 450 procuras, 2 354 preads e 7 062 SET. Os produtores das 4 544 procuras de gerações T2 e as 5 906 procuras de gerações herdadas cobrem a população inteira. Há 1 648 dependências de reutilização de slot, 334/325 duplicados retirados da fila e zero esperas por vítima ou cancelamentos. Dois ensaios falharam porque o verificador exigia uma ordem para ações simultâneas em trabalhadores independentes. Ambos estão preservados. As duas ordens em cada processo reproduzem os mesmos resultados nos seis cenários. A projeção pontual fixa a ordem do mutex, os workers, os duplicados e os resíduos observados. Contenção variável, política que muda a origem de uma reserva e custo real de integração exigem nova evidência. A relaxação admite outra escolha de worker. [Falhas e execuções](evidence-20261128-r03/provenance.json)

**Proteção de código.** Os seis processos históricos do caso natural de código avaliaram 61 IDs novos e produziram 256, com validação funcional em 6/6. Pack + fusão adiantou o primeiro conteúdo em 4,075/3,862 s contra R0 e 0,140/0,534 s contra pack sem fusão. Os quatro contrastes passaram as proteções de decode T2 e validação T1. Para atribuir os 484 acertos à tarefa de código faltam o journal das quatro filas/lanes e a entrada do banco nessa trajetória. Esse contrafactual permanece NOT_RUN_RAW_REQUIRED. O replay nominal e os oito braços fornecidos C318 conservam os seus próprios denominadores. [Comparação de código](../cpu_wave/code_chat/README.md) · [Critérios históricos por par](../../post-c320/README.md)

**Antecedente metodológico, consulta de 28 de novembro.** Coz mede o efeito de acelerar uma região introduzindo atrasos nas threads concorrentes e observando pontos de progresso. Aqui o ponto de progresso é o primeiro conteúdo final recebido. Os relógios provêm de dois pedidos do target. O replay mantém dependências e a relaxação delimita o máximo atribuível ao mecanismo. Um ensaio integrado com a ablação permanece necessário para um efeito causal no cliente. [Curtsinger e Berger, método e avaliação](https://arxiv.org/html/1608.03676) · [Antecedentes do serviço de experts](../../post-c320/literatura.md)

Na raiz do worktree, o primeiro comando verifica os artefactos publicados sem GPU, modelo ou raw privado. O segundo reabre também os journals e recibos originais.

```sh
p=research/ready-experts/request_path
python3 -IB "$p/analyse.py" --check "$p/evidence-20261128-r03"
python3 -IB "$p/analyse.py" --check "$p/evidence-20261128-r03" --archive "$TESY_PFJ_ARCHIVE"
```

**Validação local da unidade.** As quatro verificações públicas reproduzem o replay, os dois ensaios físicos e o limiar de antecipação. Os controlos negativos alteram uma linha de ranks, introduzem um expert alheio ao router, trocam dois grupos cronometrados e retiram um setor ao contador do disco. Todos foram rejeitados. A reanálise C318, os oito originais C317 e as 7 533 versões em 45 heads da consolidação passaram. Executámos 444 testes do projeto e 42 testes dos gates a partir da raiz. Uma invocação inicial a partir de `tools/` falhou ao resolver fixtures relativas à raiz. O arquivo privado `request-path-20261128-r01` contém 29 ficheiros e 1 304 850 bytes das novas campanhas, verificados após cópia sem substituição. [Manifesto do arquivo privado](private-archive.json)

```sh
python3 -IB "$p/transport_grade.py" --check "$p/evidence-transport-20261128-r01"
python3 -IB "$p/layer_release.py" grade --check "$p/evidence-layer-20261128-r01"
python3 -IB "$p/advance.py" --check "$p/evidence-advance-20261128-r01"
python3 -IB "$p/test_evidence.py"
```
