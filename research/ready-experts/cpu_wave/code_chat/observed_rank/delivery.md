# Pode um cálculo parcial avançar enquanto chegam as restantes páginas?

**MEDIDO · INCONCLUSIVE para o tempo do serviço completo com quatro leitores.** A disponibilização das primeiras 32 linhas de gate e up de todos os quatro experts antecipou-se em ambas as ordens, inclusive contra a ablação com as mesmas janelas de leitura. O join do quarteto ganhou 6,107 ms numa ordem e perdeu 6,382 ms na inversa contra a leitura integral. O operador atual aceita a entrega parcial do pack. A hipótese de que essa capacidade exija criar um backend novo fica sem sustentação neste corte. [Protocolo de quatro workers](quartet-protocol.md) · [Todos os 21 braços e preços](quartet-result.json)

## O primeiro consumidor

A rota do primeiro decode observado à posição 189 e camada 0 escolheu os experts 28, 24, 8 e 16. No pack C291, gate, down e up ocupam três trechos contíguos. Cada matriz tem 2 880 linhas de 1 530 B. Um único grupo de 32 linhas de gate e up precisa de 97 920 B lógicos. No expert 28 testámos duas leituras O_DIRECT de 49 152 e 53 248 B sobre o pack existente. Logo após essas duas conclusões, o kernel CPU MXFP4 × Q8_0 registado no C269 produziu os 64 F32 pré-bias que a execução independente do target tinha gravado. Duas leituras posteriores completaram o registo. O controlo só calculou após a leitura contígua de 13 221 888 B. Ambas as agendas pediram cada página exatamente uma vez, concluíram os mesmos bytes e usaram um buffer do mesmo tamanho.

Os dois processos em ordem inversa produziram os mesmos hashes, em 0,083 / 0,075 s por processo. É uma prova de dependências e integridade. A experiência seguinte mediu tempos. [Protocolo do primeiro rank](stripe-protocol.md) · [Janelas e saídas](stripe-result.json) · [Comandos](stripe-commands.json) · [Arquivo](stripe-archive.json)

## O que aconteceu com quatro workers

F lê uma vez por expert e calcula no fim. L faz as quatro leituras por expert e calcula no fim. E usa as mesmas quatro leituras e calcula após as duas primeiras. Cada worker possui o seu buffer até ao join. Partem juntos por barreira e calculam as mesmas 64 saídas com a ativação real. As 256 saídas são conferidas contra a captura independente e os doze componentes completos contra o manifesto depois do join de cada braço. Todas as durações vêm de um único relógio monotónico. Os números positivos abaixo significam que E chegou antes.

| Ordem dos trios | Controlo | Ganho mediano de E até às quatro contribuições | Ganho mediano de E até ao join |
|---|---|---:|---:|
| F / L / E | F, leitura integral | 23,043 ms | 6,107 ms |
| F / L / E | L, mesmas quatro janelas | 16,131 ms | 0,383 ms |
| E / L / F | F, leitura integral | 14,879 ms | −6,382 ms |
| E / L / F | L, mesmas quatro janelas | 13,821 ms | −7,239 ms |

Cada mediana abrange três pares após uma tripla de aquecimento. A amostra, a evolução natural do controlador e a sobrecarga de coordenação Python/FFI limitam a atribuição. A antecipação das contribuições foi reproduzida. O efeito da mudança no tempo para terminar a operação dependeu da ordem. A observação mínima para avaliar a sobreposição útil é ligar, no mesmo relógio, a disponibilidade dessas linhas ao início e fim do consumidor real de bias, SwiGLU e Q8_0, à conclusão do down e à barreira da camada. Na ordem inversa, o débito mediano contra a mesma agenda foi **7,239 ms por quarteto**. O consumidor teria de recuperar esse débito para adiantar a camada se os restantes preços se conservassem. A fixture mede só 32 linhas de cada uma das duas projeções e não executa o FFN completo. A margem não pode ser somada diretamente aos segundos de um pedido.

A família confirmou 5 376 valores F32 e 252 hashes de matrizes. Pediu **1 110 638 592 B** ao pack. Ao longo da janela medida o contador de leitura de todo o dispositivo avançou 2 169 216 setores de 512 B, o mesmo número de bytes. A coincidência é específica desta janela. Sob AC e com C55 recente, o monitor registou nove amostras, até 53,625 °C na CPU, 42,26 °C na GPU e 36,85 °C no NVMe. A fase que inclui os quartetos, os guardas e os hashes durou 2,221 s e o pico do cgroup foi 104 464 384 B, com cap de 256 MiB, zero swap e zero forwards. A energia total ficou desconhecida. [Comandos e versões](quartet-commands.json) · [Arquivo privado](quartet-archive.json) · [Decisão para o perfil do portátil](../../../../../docs/architecture/0005-execucao-local-por-perfil.md)

```sh
unit=research/ready-experts/cpu_wave/code_chat/observed_rank
python3 -IB "$unit/review_delivery.py"
python3 -IB "$unit/review_delivery.py" --archive "$TESY_QUARTET_ARCHIVE"
```
