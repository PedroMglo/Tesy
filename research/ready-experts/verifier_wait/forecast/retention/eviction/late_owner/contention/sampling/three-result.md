# Quanto custa a leitura que sobrevive quando dois pesos vêm da RAM?

**NO_GO para justificar um novo motor pela contenção de leitura nestes preços.** Servir um ou dois dos três experts pela RAM adiantou o último miss nas duas ordens dos quatro grupos no portátil. A projeção mais favorável das seis classes ainda chega a **10,214 s** no primeiro conteúdo final em P106. No mesmo extremo P97 daria 9,928 s. O prazo é 10 s nos dois registos do mesmo turno. [Protocolo anterior aos ensaios](three-protocol.md) · [Preços por fase e seleção](evidence-three-20261128-r01/projection.json)

| READ / hits | Seleção | Variação H−D OFF no último sobrevivente, ms D/H e H/D | Intervalo admitido da redução do pread |
|---|---|---:|---:|
| 3 / 1 | inicial | −4,287 / −3,936 | 19,3769–32,9559% |
| 3 / 1 | independente | −3,892 / −3,981 | 22,5967–35,9448% |
| 3 / 2 | inicial | −7,075 / −6,952 | 56,5009–66,2314% |
| 3 / 2 | independente | −7,438 / −6,647 | 0–100%, calibração rejeitada |

A mediana ON/OFF de uma das quatro calibrações na seleção independente 3/2 foi 103,8554%, acima dos 103% congelados. A envolvente oferece toda a redução dessa classe no extremo favorável. Os outros três grupos passaram as quatro calibrações. Cada pread da fase de preço individual teve pelo menos 15 observações positivas, e todas as seleções e direções foram conservadas. [Chaves, calibrações, cobertura e custos das cópias](evidence-three-20261128-r01/device.json) · [2 016 ensaios individuais](evidence-three-20261128-r01/service.txt)

| Hipótese no melhor extremo | Primeiro final P97 / P106, s | Decode de 47 tokens P97 / P106, s |
|---|---:|---:|
| Envolvente, custos ordinários | 10,799 / 11,831 | 5,743 / 5,920 |
| Créditos CPU e observador, seleção inicial | 9,987 / 10,271 | 5,782 / 5,957 |
| Mesmos créditos, seleção independente | 10,055 / 10,334 | 5,776 / 5,954 |
| Mesmos créditos, envolvente | 9,928 / 10,214 | 5,743 / 5,920 |

Os 711 créditos de cálculo e toda a captura e preparação da reserva já são gratuitos no extremo favorável. Em P106 o primeiro final integral deste extremo é 10,861 s antes da dedução de 646,428 ms pelo observador. Mesmo com a dedução faltam **214,467 ms**. Com serviço e relógio ordinários o défice é **1,831 s**. Os custos de coordenação e de 26,055 GB lógicos de captura aumentariam a obrigação. Estes limites são condicionais à transferência das taxas das populações selecionadas para as interseções dos journals. Uma mudança no serviço fora dessas interseções abre uma hipótese diferente. O contraste seguinte interroga diretamente o custo da dependência entre duas tiles. [Decisão sobre as duas primeiras classes](README.md) · [Protocolo da comparação entre arquiteturas](pipeline-protocol.md)

O leitor pediu 60 133 146 624 B em 4 548 leituras do pack e verificou 18 180 hashes de matrizes. Concluiu em 35,143 s, com 163 557 376 B de pico e zero swap. As máximas amostradas foram 65,625 °C na CPU, 48,68 °C na RTX e 45,85 °C no NVMe. Energia total desconhecida. A fixture usou os bytes do modelo e fez zero forwards e zero pedidos HTTP. M3 PARTIAL e M4 NOT_MET. [Proveniência e comandos](evidence-three-20261128-r01/provenance.json) · [Arquivo privado](evidence-three-20261128-r01/archive.json)

```sh
S=research/ready-experts/verifier_wait/forecast/retention/eviction/late_owner/contention/sampling
python3 -IB "$S/three.py" check "$S/evidence-three-20261128-r01"
```
