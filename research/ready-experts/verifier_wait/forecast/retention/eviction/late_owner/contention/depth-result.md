# Quais das seis populações podem mudar a decisão sobre o backend?

**NO_GO para substituir o executor neste perfil com base na contenção entre leituras.** Nos 720 ensaios do portátil, servir os hits em RAM adiantou o último peso ainda no disco nas duas ordens de todas as seis populações. Duas permitiram também qualificar o tempo de cada leitura individual. Aplicando a maior redução qualificada dessas duas e dando de graça todo o tempo simultâneo das outras quatro, o primeiro conteúdo final com os preços ordinários ficaria em **9,897 / 10,997 s** nos dois registos do mesmo turno. Estes são pisos condicionais às taxas selecionadas e aos custos mantidos fora da interseção. [Pré-registo físico](mixed-device.md) · [Projeção dos dois relógios do cliente](evidence-depths-20261128-r01/projection.json)

**INCONCLUSIVE para a composição mais favorável.** A banda repartida em partes iguais entre os READ dá 10,149 / 10,422 s até ao primeiro final, mesmo com as concessões da CPU, a captura gratuita e o crédito do observador de P106. Para chegar aos dois alvos com um único corte uniforme seria preciso retirar pelo menos 47,0731% / 57,7721% do tempo em que os misses e os hits competiam de facto. Se o benefício durar desde o primeiro concorrente até ao fim de cada READ, a condição muda para 41,1150% / 50,8154% do sufixo. Estes cenários conservam cada nanosegundo por worker, fase e camada, e dão os dois extremos conhecidos de zero e de todo o READ elegível. [Protocolo temporal](mixed-protocol.md) · [Partição e cortes](evidence-depths-20261128-r01/mixed.json)

## O que o NVMe mediu

Em cada população repetimos uma seleção de pesos que apareceu nos dois processos C281. A escolha foi lexicográfica pela ordem das reservas do target. As quatro threads aguardavam no mesmo ponto de emissão. A tabela mostra, com observação individual desligada, a diferença emparelhada H menos D na chegada do último miss. As cópias e a verificação dos destinos vinham depois. Cada ordem tem sete pares. As calibrações verificaram a barreira dos sobreviventes com o tracer individual OFF/ON, nos dois modos e nas duas ordens. Para usar os rácios individuais, as quatro medianas de calibração tinham de estar entre 97% e 103%. [Leitor](mixed.cpp.in) · [Medições individuais nos 720 ensaios](evidence-depths-20261128-r01/service.txt)

| READ em curso / hits em RAM | Populações comuns | H−D na ordem D/H, ms | H−D na ordem H/D, ms | Calibração individual | Redução qualificada da duração do pread por lane e ordem |
|---|---:|---:|---:|---|---:|
| 2 / 1 | 201 | −4,390 | −4,422 | fora do intervalo | desconhecida |
| 3 / 1 | 247 | −5,022 | −4,202 | fora do intervalo | desconhecida |
| 3 / 2 | 106 | −6,752 | −6,438 | fora do intervalo | desconhecida |
| 4 / 1 | 166 | −3,338 | −4,872 | fora do intervalo | desconhecida |
| 4 / 2 | 104 | −8,332 | −7,669 | passou | 48,0870–49,0665% |
| 4 / 3 | 42 | −11,858 | −7,137 | passou | 67,1949–68,2002% |

H e D mantiveram os mesmos destinos. Os SHA das três matrizes passaram nos 7 260 controlos iniciais e de destino. Cada destino foi alterado depois da verificação para detetar uma cópia omitida no ensaio seguinte. A projeção usa de zero a 100% nos quatro níveis sem calibração. Nos outros dois usa a menor e a maior mediana entre as lanes e ordens, com arredondamento para fora. Transferir estas taxas de um grupo de offsets para os restantes grupos da mesma classe é uma hipótese. O firmware e os instantes de despacho podem alterar a duração. [Recibo e quatro rácios de calibração por grupo](evidence-depths-20261128-r01/device.json)

| Preços do pedido | Primeiro final P97, s | Primeiro final P106, s | Decode de 47 tokens P97 / P106, s |
|---|---:|---:|---:|
| Ordinários, extremo mais favorável dos seis grupos | 9,897 | **10,997** | 5,326 / 5,528 |
| Com créditos CPU e observador, extremo mais favorável | 8,973 | **9,316** | 5,326 / 5,528 |
| Com os mesmos créditos, extremo de menor aceleração | 11,075 | **11,313** | 6,366 / 6,535 |

P106 tem também o tempo integral antes de descontar os 646,428 ms do observador. Nos dois extremos com créditos CPU esse primeiro final é 9,963 e 11,959 s. Todos os cenários oferecem a aquisição inicial e os 26,055 GB lógicos de capturas do banco renovável. O tempo do primeiro conteúdo, o trabalho CPU elegível e as capturas continuam a decidir a viabilidade no pedido completo.

**Observação mínima.** Enumerámos as 16 combinações dos quatro níveis sem relógio individual qualificado, em cada extremo das duas classes medidas. Para que a resposta possa entrar no prazo, o único conjunto mínimo que sozinho permite a travessia nas extremidades é **2/1 e 4/1**. Com as outras classes ignoradas pode exigir taxas bem superiores. Mesmo atribuindo 100% a todos os restantes níveis desconhecidos e as maiores taxas medidas aos dois conhecidos, a redução em 2/1 tem de atingir 5,3762% e a de 4/1 tem de atingir 0,5348%. São condições necessárias individuais. Uma observação suficientemente baixa em qualquer uma pode fechar o cenário. Uma observação mais alta nos dois grupos exige repricing conjunto e custo de captura. O próximo discriminante é cronometrar os pread individuais destes grupos com um relógio independente qualificado, mantendo o controlo OFF e ao mesmo tempo os cortes reais do consumidor. [Todos os subconjuntos, dois inteiros de cada limiar e margens](evidence-depths-20261128-r01/thresholds.json)

## Reprodução

```sh
D=research/ready-experts/verifier_wait/forecast/retention/eviction/late_owner/contention
E="$D/evidence-depths-20261128-r01"
python3 -IB "$D/mixed.py" --check "$E/mixed.json"
python3 -IB "$D/depths.py" check "$E"
python3 -IB "$D/depth_thresholds.py" --projection "$E/projection.json" --check "$E/thresholds.json"
python3 -IB "$D/test_mixed.py"
```

**Recursos e falhas.** O leitor completou 1 820 pedidos alinhados e 24 063 836 160 B no NVMe em 14,031 s. O pico do scope foi 202 518 528 B e o swap ficou a zero. Os máximos entre 19 amostras foram 62,875 °C CPU, 45,9 °C na RTX e 42,85 °C no NVMe. A energia total permanece desconhecida. A primeira preparação do build e do plano falhou ao calcular o hash do programa. Na identidade seguinte, o monitor interrompeu o leitor por atingir o limite de paragem do scope. O systemd registou 232,5 MiB de pico. A análise offline passou a carregar só no planeamento e na avaliação, e cada grupo passou a reservar staging e destino apenas para os participantes. Outra janela C55 passou e a identidade r03 terminou com a mesma política. As duas preparações e o ensaio interrompido estão conservados no arquivo local. Houve zero forwards e zero pedidos HTTP. O melhor pedido observado e os estados M3 PARTIAL e M4 NOT_MET permanecem os da qualificação do produto. [Comandos, recursos e falhas](evidence-depths-20261128-r01/provenance.json) · [Manifesto do arquivo](evidence-depths-20261128-r01/archive.json)
