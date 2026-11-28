# Chegar mais cedo ao primeiro conteúdo quando um dos pesos já está na RAM

**INCONCLUSIVE para a composição mais favorável, NO_GO para financiar um novo backend a partir destes quatro grupos.** Em 2 016 ensaios no NVMe interno, servir um expert pela RAM encurtou também o tempo da chamada de leitura dos experts que continuaram no disco. Com os preços ordinários e as maiores reduções compatíveis, o primeiro conteúdo final fica em 10,542 / 11,578 s nos dois registos do mesmo nominal. O melhor pedido HTTP medido continua em 17,689 s e 5,357 tok/s. [Protocolo congelado](protocol.md) · [Preço por fase, ordem e processo](evidence-20261128-r01/projection.json)

| Leituras / hits | Seleção de offsets | Intervalo da redução do pread sobrevivente | H−D no último sobrevivente com observação OFF, D/H e H/D | Medianas de calibração ON/OFF, mín.–máx. |
|---|---|---:|---:|---:|
| 2 / 1 | inicial | 43,5433–56,5261% | −4,396 / −4,211 ms | 99,750–100,622% |
| 2 / 1 | independente | 38,1134–52,1222% | −3,504 / −3,441 ms | 98,649–100,269% |
| 4 / 1 | inicial | 25,7072–38,9529% | −4,539 / −4,994 ms | 99,461–100,878% |
| 4 / 1 | independente | 5,8652–28,2821% | −3,897 / −3,958 ms | 98,607–100,572% |

Cada grupo passou os quatro testes de neutralidade. O supervisor viu o pread correto pelo menos 22 vezes em cada leitura individual usada para o preço. A largura mediana da duração delimitada variou entre 0,563 e 0,791 ms segundo a lane, a ordem e o braço. Os intervalos da tabela cobrem as medianas emparelhadas entre lanes e ordens. A distribuição de todos os grupos de offsets da máquina continua desconhecida. O recibo inclui também o tempo de todos os READ, o drain, as chaves, os índices de seleção e a cobertura de cada lane. [Recibo físico](evidence-20261128-r01/device.json) · [Ensaios individuais](evidence-20261128-r01/service.txt)

| Preço do primeiro conteúdo final | P97, s | P106, s |
|---|---:|---:|
| Custos ordinários, envolvente das duas seleções | 10,542–11,486 | 11,578–12,512 |
| Créditos CPU e do observador, seleção inicial | 9,663–10,464 | 9,953–10,726 |
| Mesmos créditos, seleção independente | 9,785–10,699 | 10,071–10,942 |
| Mesmos créditos, envolvente | 9,663–10,699 | 9,953–10,942 |

No cenário com créditos, os 711 descontos CPU são condicionais. Apenas P106 desconta também 646,428 ms anteriores à produção. O preço integral de P106 no melhor extremo é 10,599 s antes desse desconto. A seleção independente por si só falha o prazo mesmo no extremo mais generoso. A envolvente deixa apenas **47,355 ms** de margem em P106, dando ainda 100% de redução do período simultâneo nas classes 3/1 e 3/2 e oferecendo os 26,055 GB de capturas. O tempo projetado para 47 tokens de decode é 5,601–6,073 s em P97 e 5,790–6,238 s em P106. Os dois registos têm relógios separados. M3 PARTIAL e M4 NOT_MET.

**Próximo discriminante.** Medir as duas classes de três leituras com uma e duas fontes em RAM na mesma fixture. A comparação física com dois hits exige buffers autenticados independentes. Um eventual ganho só justifica mudar a fronteira do motor se sobreviver à cobrança no pedido e se a fronteira atual impedir a implementação.

**Recursos.** O leitor pediu 66 796 978 176 B em 5 052 leituras e verificou 18 180 hashes de matrizes. A aquisição durou 37,621 s, com pico de 177 053 696 B no scope e swap zero. As máximas amostradas foram 63,25 °C na CPU, 48,08 °C na GPU e 45,85 °C no NVMe. Energia desconhecida. A primeira preparação do plano falhou ao criar threads para o índice Git sob o limite de 1 GiB. Usámos outra identidade, serializando apenas o acesso ao índice nesse comando. Houve zero forwards e zero pedidos HTTP. [Proveniência, custos e comandos](evidence-20261128-r01/provenance.json) · [Arquivo privado verificado](evidence-20261128-r01/archive.json)

```sh
S=research/ready-experts/verifier_wait/forecast/retention/eviction/late_owner/contention/sampling
python3 -IB "$S/sampled.py" check "$S/evidence-20261128-r01"
python3 -IB "$S/test_sampler.py"
```
