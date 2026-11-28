# Quanto pode custar prever dois tokens antes do 120B?

**NO_GO para construir um backend dedicado ao 20B serial mantendo o prefill e o trabalho exterior dos controlos W.** O proponente antecipou corretamente 30 de 32 IDs no turno nominal e 162 de 188 no código, contando o EOG medido no seguimento. Na CPU do portátil, produzir as propostas nominais ocupou 1,357 s antes do primeiro conteúdo final. Essa janela só dispunha de 0,340 s em W3 e 0,839 s em W4 se o verificador fosse instantâneo. O melhor turno nominal medido no cliente continua em **17,689 s e 5,357 tok/s**, com pack e fusão CPU. A demonstração de M3 permanece PARTIAL e a de M4, NOT_MET. [Controlos físicos](../cpu_wave/README.md) · [Protocolo congelado](protocol.md) · [Recibo inicial](evidence-20261128-r01/study.json) · [Correção do EOG e combinação com o prefill](joint/README.md)

## Aceitação medida em contexto

O 20B original leu os mesmos IDs que o 120B recebeu nas duas conversas. Em dois contextos independentes por caso, testámos alimentação serial e propostas com rollback. Todas as 201 088 posições do vocabulário coincidiram nas peças, atributos e marca EOG. O SHA-256 das linhas completas de logits finitos do 20B coincidiu nas duas passagens no fim de cada prompt e em cada um dos 301 prefixos gerados. O 120B forneceu os tokens autênticos de referência. A experiência física fez forwards apenas no 20B em CPU. O 120B ainda tem de avaliar os novos blocos no percurso integrado. A prova abrange a trajetória greedy destes dois pedidos.

| Trajetória T2 | Coincidências greedy em todos os prefixos | Blocos de duas propostas | Blocos com 0 / 1 / 2 acertos | IDs antecipados | Avanços do target |
|---|---:|---:|---:|---:|---:|
| Nominal153 | 43/46 | 16 | 1 / 0 / 15 | **30/32** | 16 blocos, 0 seriais de cauda |
| Código61 | 230/255 | 94 | 7 / 12 / 75 | **162/188** | 94 blocos, 0 seriais de cauda |

O replay inicial fez a cauda de código em serial porque conhecia a posição do EOG. A fixture seguinte mediu os dois forwards no último prefixo e autenticou a proposta de EOG do 20B. As linhas de código e os preços atuais já incluem esse bloco, combinando as duas execuções. [Correção da fronteira terminal](joint/README.md)

O denominador do decode inclui a âncora que o prefill produziu, 47 e 256 IDs no total. Os dois controlos de cada caso tinham os mesmos 2 044 IDs em cache. A experiência do proponente recompôs o prompt completo em cada passagem. Esse prefill isolado custou 33,324–33,473 s no nominal e 31,978–31,980 s no código. Concedemos-lhe custo zero nas projeções seguintes. O valor a pagar por um auxiliar que acompanhe T1 e receba apenas o incremento de T2 continua desconhecido.

## Preço máximo do target com o proponente em série

| Controlo W de trabalho idêntico | Primeiro final físico | Decode físico | Primeiro final com verificação grátis e draft pago | Preço máximo por bloco até ao primeiro final | Preço máximo por bloco no decode |
|---|---:|---:|---:|---:|---:|
| Nominal W3 | 18,533 s | 9,133 s | 11,606 s | −100,4 ms | 367,9 ms |
| Nominal W4 | 17,689 s | 8,774 s | 11,107 s | −69,2 ms | 367,9 ms |
| Código W3 | 28,708 s | 58,360 s | 12,503 s | 476,6 ms | 505,2 ms |
| Código W4 | 29,029 s | 58,357 s | 12,789 s | 477,6 ms | 505,2 ms |

Cada linha mantém os intervalos W exteriores e o serial de cauda. O nominal exige 10 s e 6 tok/s. No código, cada preço conserva o tempo da respetiva fase no controlo. Os 16 blocos nominais chegam à amostra 45, que produziu o primeiro fragmento final. No código, os primeiros 34 chegam à amostra 85. O preço do auxiliar inclui os dois forwards reais e o avanço de KV ou rollback dos blocos anteriores ao corte. No nominal são 1,357 s de propostas e 0,589 s para voltar a alinhar a história. Argmax, hashing, coordenação, disputa e manutenção posterior ao último bloco do corte recebem custo zero. Os clocks do cliente e do produtor conservam a sua origem. A projeção favorável concede o intervalo até à amostra que produziu o fragmento. O feed comprovadamente anterior ocorreu 167–176 ms antes dessa amostra no nominal e 226–228 ms antes no código.

## Um limite que abrange proponentes melhores

O verificador de agenda permite escolher com conhecimento do futuro entre um passo serial e qualquer bloco legal. Há um único percurso para o primeiro conteúdo e o decode completo. O recibo inclui um percurso testemunha e o primeiro preço inteiro em nanossegundos que deixa de admitir essa combinação. O teste por enumeração independente cobre chegadas ao corte em posições diferentes e rejeições. [Método prospetivo](frontier.md) · [Testemunhas](evidence-20261128-r01/frontier.json) · [Teste do grafo](../../../tests/test_draft20_budget.py)

| Hipótese antes de verificar o bloco | Máximo por bloco para cumprir os dois critérios em W3 / W4 | Redução necessária antes do primeiro conteúdo se o bloco custar um passo serial mediano |
|---|---:|---:|
| Auxiliar perfeito, gratuito | 22,693 / 55,964 ms | 2,432 / 1,867 s |
| Acertos reais do 20B, auxiliar gratuito | 21,275 / 52,466 ms | 2,492 / 1,917 s |
| Acertos reais, forwards necessários ao preço isolado da CPU | Falha já a 0 ms | **3,700 / 3,125 s** |

No último cenário, o segundo forward é gratuito quando o primeiro ID falha. Todo o alinhamento, a escolha com futuro perfeito e as posições não propostas também são gratuitos. Mesmo assim, com verificação instantânea o primeiro final mais cedo seria **10,997 / 10,498 s**. Na última coluna o preço atribuído a B3 é 184,846 / 180,419 ms, a mediana serial do respetivo W. Há uma agenda que satisfaz os 6 tok/s nessa simulação. Ainda seria preciso retirar os segundos indicados ao prefill ou a outro trabalho exposto antes do primeiro fragmento. Os 3,700 / 3,125 s são condições de reabertura. A velocidade de um servidor conjunto continua por medir.

## O que o executor atual já fez

O pedido real de código do PR tinha 46 oportunidades com o proponente por histórico. Das 94 do 20B, 21 começam no mesmo prefixo e nove reproduzem os dois IDs da proposta anterior. Em **oito**, o 120B confirmou fisicamente os dois IDs e o bónus, nos dois servidores ON anteriores. Esses oito intervalos ocuparam 4,744 e 4,727 s. Nos outros 86 falta uma observação direta equivalente. Se até os preços desses oito se mantivessem depois das novas escolhas, os restantes blocos teriam em média **497,0–497,2 ms** disponíveis no decode e os 30 por identificar antes do primeiro final teriam **461,2–463,0 ms**. A história anterior da cache e das rejeições pode mudar todos os preços. [Reconciliação e posições confirmadas](evidence-20261128-r01/coverage.json) · [Medição anterior com o 120B](../cpu_wave/code_chat/price/README.md)

Os quatro W atribuíram 12 606,81 MiB à cache primária de experts em RAM e 5 547,00 MiB à da RTX. O 20B stock declarou um buffer de pesos mapeado de 11 536,18 MiB. Para o manter **todo residente** juntamente com o primário atual, só os pesos e os slots excederiam o cap de RAM de 20 GiB em pelo menos 3 662,97 MiB com a colocação CPU do ensaio. Até redistribuindo esses buffers entre toda a RAM admitida e os 8 188 MiB físicos da RTX faltariam pelo menos 1 021,96 MiB. Concedemos gratuitamente KV, workspace, restantes pesos do target e as reservas preventivas. Páginas não residentes, representação diferente ou partilha de bytes exigem outra conta e outro preço de serviço. O banco secundário de 353 experts consumiria ainda 4 666 377 600 B de payload. Combinar os ganhos requer que ambos caibam e que o trabalho desapareça antes da mesma peça do cliente. [Recibos dos buffers](evidence-20261128-r01/coverage.json) · [Banco renovável](../layer/prefix/wave/tier-result.md)

**Decisão de investimento.** Preservar o executor atual e R0 slots40-persistent como referência operacional. Há evidência para estudar um auxiliar com menos memória e um prefill mais rápido em conjunto. Para justificar outro backend, a próxima demonstração precisa de uma colocação que caiba e de um corte de trabalho exposto da escala acima. Uma fixture de preço do target pode forçar os pares reais sob os três braços de exatidão e a ablação. Só uma conversa com propostas causais, o recurso partilhado e os dois relógios do cliente poderá qualificar o produto. A aceitação encontrada aqui e a indexação antecipada de experts são mecanismos distintos.

## Execução e reprodução

Protocolo em `60419dd4`, medição em árvore limpa `e8a64685`, fronteira conjunta congelada em `6360fc8f` antes da pontuação. O build stock independente reproduziu o mesmo ELF de 45 008 B. No portátil, C55 passou em 60,008 s, C118 em 60,135 s, a verificação integral do SHA do 20B em 12,603 s e o processo em 170,830 s. Pico de 12 922 945 536 B no scope, zero swap, 95,5 °C CPU, 61,3 °C GPU, 41,85 °C NVMe. A GPU fez zero forwards. As amostras de potência GPU somam 621,3 J em 170,13 s, a energia total do portátil ficou desconhecida. O GGUF 20B estava no SSD USB e o original 120B no NVMe interno. O arquivo privado exclusivo guarda 26 ficheiros com 1 542 709 B. Quatro testes locais desta unidade cobrem a contabilização e a seleção conjunta. [Comandos, limites e hashes](evidence-20261128-r01/provenance.json) · [Manifesto privado](evidence-20261128-r01/archive.json)

Na validação local passaram 440 testes do repositório, 42 testes adicionais dos gates e Ruff. A reanálise compacta e a verificação C317 com os oito originais correram com êxito, e a consolidação conferiu os 45 heads históricos. O replay do arquivo selado reproduziu a cobertura dos blocos, os intervalos e os limites de memória.

~~~sh
unit=research/ready-experts/draft20
e="$unit/evidence-20261128-r01"
python3 -IB "$unit/review.py" --check "$e/study.json"
python3 -IB "$unit/frontier.py" "$e/study.json" --check "$e/frontier.json"
pytest -q tests/test_draft20_budget.py
~~~
