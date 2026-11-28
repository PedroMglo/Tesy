# Escolha de backend com residência finita e dados disponíveis ao router

**NO_GO para investir agora num backend inteiramente novo neste portátil.** O executor atual aceitou uma segunda origem de pesos e preservou os resultados numéricos do GPT-OSS-120B até ao fim da resposta. Mesmo conhecendo o futuro, servir 75 aquisições na RAM deu sinais opostos na duração do prefill. O limite abaixo fecha também a retenção de dois experts adicionais por etapa aos preços medidos. Para mudar a decisão, um executor diferente tem de identificar a espera que consegue retirar do pedido e o custo de a retirar. [Experiência no modelo e resultado de cada par](consumer-result.md)

No portátil, revelar ao leitor os experts por camada custou mais **203–218 ms** do que revelar todos os offsets à entrada da chamada. Mesmo assim, o leitor terminou em **3,347–3,419 s** perante um orçamento de prefill de 3,484 s no braço nominal mais exigente. Esta medição concede um espelho perfeito dos pesos disponíveis anteriormente. Com apenas dois lugares adicionais em cada etapa, a política que usa o texto já admitido recupera sete das 166 oportunidades. O seu primeiro conteúdo final projetado mais rápido fica em **10,372 s**. Esta composição recebe **NO_GO**. [Pré-registo](protocol.md) · [Recibo de capacidade](evidence-20261128-r01/finite.json)

## O que cabe na memória

Das 892 faltas do banco de referência, 166 ocorrem depois de o expert perder a última cópia primária ou secundária dentro da chamada. As 112 da frente e 54 de trás têm janelas de retenção diferentes. Para conservar **todas**, os picos são de **74** lugares na frente e **26** atrás, ou 1 322 188 800 B de memória adicional reservada em dois bancos fixos. Cada uma das quatro posições adicionais realmente avaliadas ocupa 13 221 888 B. O verificador reproduz o dono e a geração em 1 263 reservas no prefill e o estado dos dois bancos e do primário à entrada do decode. Uma transferência direta do banco para o primário preserva o expert. [Testemunhos por reserva e origem](evidence-20261128-r01/finite.json)

| Fonte dos pesos | Leituras evitadas | Capturas e volume de payload | Primeiro final P97 | Primeiro final P106 |
|---|---:|---:|---:|---:|
| Reuso desligado | 0 | 0 | 10,386–10,611 s | 10,488–10,713 s |
| Recência na expulsão | 10 | 844 / 11,157 GB | 10,375–10,601 s | 10,469–10,694 s |
| Pontuação lexical T1 | 7 | 29 / 0,383 GB | 10,372–10,597 s | 10,472–10,697 s |
| Melhor contagem com 2+2 lugares, seleção futura | 32 | 32 capturas ideais | 10,359–10,584 s | 10,455–10,680 s |
| Espelho ilimitado, seleção futura | 166 | captura gratuita | 9,926–10,151 s | 10,005–10,230 s |

As durações são **TRACE_DERIVED**. Atribuem custo zero à captura, pagam os três SET e concedem o crédito das adjacências originais. Mostram os extremos das duas repetições e dos dois cortes de streaming de cada journal com o mesmo decode lexical. A receita lexical teria de retirar pelo menos outros 371,870 ms no seu extremo mais favorável e 697,124 ms no mais exigente para chegar a 10 s. O orçamento adicional disponível já é negativo. As 29 capturas incluem 25 saídas de um banco RAM, uma do primário CPU e três do primário GPU. A tabela de scores contém agregados por tile, camada e expert, sem texto nem IDs do prompt. [Pontuações congeladas](evidence-20261128-r01/scores.json.gz) · [Comparação dos oito braços](evidence-20261128-r01/finite.json)

## Limite para qualquer escolha nos quatro lugares

Maximizar a contagem de acertos pode privilegiar uma leitura curta em vez de uma leitura que atrasava a camada. O verificador examinou todas as combinações de intervalos de retenção compatíveis com os dois lugares de cada etapa. Calculou conjuntamente o custo das leituras e das três cópias que chegam ao mesmo site. Para obter um piso favorável, permitiu inclusive que cada um dos 16 caminhos do grafo escolhesse as suas próprias capturas gratuitamente. O caminho que ainda demorava mais atravessa as cinco tiles na primeira etapa e a última tile na segunda. [Protocolo da prova](bound.md) · [Verificador e controlos](bound.py)

| Journal e serviço fixos | Piso do prefill 5 + 148 | Menor piso para o primeiro final | Maior piso nos cortes avaliados |
|---|---:|---:|---:|
| P97 | 3,961630 s | 10,243373 s | 10,468676 s |
| P106 | 4,036909 s | 10,328022 s | 10,553029 s |

**FORMAL, sob os preços congelados.** Faltam pelo menos 243 ms até no melhor braço. O limite abrange a captura na última perda de propriedade, os dois buffers por etapa, as cinco tiles, o decode lexical congelado e 4,5 GB/s. Alterar o tempo de serviço, a capacidade ou as dependências pode alterar o limite. Os dois journals provêm do mesmo histórico nominal e mantêm relógios independentes. [Oito combinações de repetição e corte, custos e caminhos](evidence-20261128-r01/bound.json)

## Quanto custa esperar pela informação do router

Todos os braços físicos pedem 34 + 692 registos genuínos ao mesmo pack do 120B. O controlo F mantém uma fila por retorno externo, ordenada por offset. R mantém a ordem dos sites de R0, fecha a fila antes da camada seguinte e ordena os pesos dentro da camada. Ambas as agendas têm quatro buffers e tratam todos os pedidos do site como imediatamente conhecidos. A execução real ainda calcula o router, faz cópias, executa as camadas e drena o trabalho. O pré-teste autenticou integralmente os 726 registos distintos. Cada acesso cronometrado verificou nove marcadores. Os grupos que ficaram vazios conservam a sua posição no verificador. [Plano e avaliador](release.py) · [Recibo físico](evidence-20261128-r01/release.json)

| Ordem | Chamada de 5 | Chamada de 148 | Total no leitor | Grupos com dados | Submissões em lotes de até quatro | Folga no braço mais exigente |
|---|---:|---:|---:|---:|---:|---:|
| F1 | 166,547 ms | 3 034,404 ms | 3 200,951 ms | 2 | 182 | 282,929 ms |
| R1 | 174,527 ms | 3 244,756 ms | 3 419,282 ms | 157 | 247 | 64,598 ms |
| R2 | 158,985 ms | 3 188,066 ms | 3 347,051 ms | 157 | 247 | 136,830 ms |
| F2 | 156,498 ms | 2 987,124 ms | 3 143,622 ms | 2 | 182 | 340,259 ms |

O número de lotes parciais subiu de 1 para 129. O custo adicional junta duas causas, a alteração da ordem dos offsets e o menor paralelismo permitido no fim de um site. Estes dois pares não as identificam separadamente. Os 64,598–136,830 ms de folga física pagariam **todo** o trabalho adicional que ficasse exposto no caminho mais exigente. A projeção de cliente com espelho ilimitado, sobreposição total e o decode anterior continua **INCONCLUSIVE**, 9,926–10,230 s. São dados de um histórico nominal. Código e medições de cliente nos limiares completos de M3 e M4 exigem outros recibos. [Braços e preços por journal](evidence-20261128-r01/release-grade.json)

O leitor decorreu durante 20,239 s com 119 603 200 B de pico no scope, zero swap, CPU a 55,375 °C, GPU a 43,23 °C e NVMe a 46,85 °C. Pediu 47 995 453 440 B no total com paridade. O contador do dispositivo inclui o restante sistema. Estes braços não carregaram o modelo para inferência. O ensaio separado do consumidor usa o GGUF original. [Proveniência e comandos](evidence-20261128-r01/provenance.json) · [Protocolo do consumidor](consumer.md)

A 28 de novembro de 2026, o antecedente de comparação mais próximo para o leitor é o SSD-LLaMA, que agrupa os pesos de um expert e começa a transferência para VRAM assim que a respetiva leitura termina. A avaliação dos autores inclui RTX 5090 e outros modelos. A diferença testável aqui é o preço de restringir a emissão ao router real de um único prefill com igual volume no NVMe do portátil. Bevy antecipa o trabalho de outro pedido enquanto o primeiro espera. Nesta conversa só o trabalho do próprio histórico é elegível. Mantemos BROAD_NOVELTY_NO_GO / ENGINEERING_AND_MEASUREMENT_GO. [SSD-LLaMA, §§4.1 e 5.1](https://arxiv.org/html/2609.18110v1#S4.SS1) · [Bevy, §§3 e 5](https://arxiv.org/html/2611.04794v1#S3)

## Reprodução sem modelo

A partir da raiz do checkout, os recibos públicos permitem recalcular as contagens de retenção, o limite temporal para todos os conjuntos, o custo da emissão por camada, o efeito condicional nas últimas publicações e os vereditos dos braços físicos.

```sh
d=research/ready-experts/verifier_wait/forecast/retention/eviction
e="$d/evidence-20261128-r01"
python3 -IB "$d/retention.py" grade --scores "$e/scores.json.gz" --check "$e/finite.json"
python3 -IB "$d/bound.py" --finite "$e/finite.json" --check "$e/bound.json"
python3 -IB "$d/release.py" grade --observed "$e/release.json" --check "$e/release-grade.json"
python3 -IB "$d/publications.py" --check "$e/publications.json"
python3 -IB "$d/consumer_run.py" check "$e/consumer-grade.json"
```

A versão de cada programa, os comandos de aquisição física, os hashes do modelo, dos inputs e das bibliotecas, os limites de recursos e os oito tamanhos e hashes históricos C317 estão no [registo de proveniência](evidence-20261128-r01/provenance.json). A reanálise histórica reproduziu os oito braços C318 e o verificador de consolidação conferiu 45 heads e 7 533 versões de ficheiro. O controlo operacional continua R0 slots40-persistent. M3 PARTIAL e M4 NOT_MET.
