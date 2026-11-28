# Conservar um frame no executor existente

**MEDIDO no portátil.** Nas nove visitas da call de 148, HOLD entregou os mesmos 71 registos em **262,570 e 269,788 ms**. RELOAD levou **312,472 e 318,305 ms**. Manter os onze pesos poupou 49,902 e 48,517 ms de serviço local nos dois pares. Todas as nove visitas tiveram sinal favorável nas duas ordens. No replay do pedido, a agenda só consegue converter em tempo do cliente 23,926 e 8,419 ms quando os READ e SET desses pesos passam a custo zero. Propagar o ganho ao pedido e cumprir M4 continua por demonstrar. [Critérios anteriores ao preço](visit-protocol.md) · [Recibo por visita](evidence-visit-20261128-r01/decision.json) · [Dois relógios do cliente](switch.md)

| Braço | Registos NVMe no preço | Lotes despachados | Preparar os 11 residentes, ms | Entrega completa à fixture, ms |
|---|---:|---:|---:|---:|
| RELOAD 1 | 71 | 22 | 56,657 | 312,472 |
| HOLD 2 | 60 | 21 | 55,543 | 262,570 |
| HOLD 3 | 60 | 21 | 57,430 | 269,788 |
| RELOAD 4 | 71 | 22 | 54,982 | 318,305 |

Os dois papéis tiveram os mesmos quatro leitores e três frames de retenção. A formação paga os pesos de entrada em cada visita antes do cronómetro, nos quatro braços. O desconto físico do período medido foi de 145 440 768 B por braço HOLD. Verificámos os 213 hashes das três matrizes dos 71 registos distintos, 2 556 sentinelas na entrega e outras 396 nas entradas. A paridade, as entradas e os quatro braços pediram 4 984 651 776 B ao pack. A contagem física foi de 9 735 648 setores de 512 B no dispositivo inteiro. Os trabalhadores drenaram. Os 2,177 s do filho incluem a paridade e o encerramento. A execução registou 147 394 560 B de pico no cgroup, zero swap e máximos amostrados de 49,625 °C CPU, 39,1 °C GPU e 36,85 °C NVMe. A GPU não executou o modelo. [Observação de transporte e proveniência](evidence-visit-20261128-r01/reads.json.gz)

O limite de memória que mantém residentes os pesos necessários e o estado terminal ficou em 1 252 frames nas 125 visitas, incluindo uma retenção conservadora para parking. A construção serial precisava até aqui de conhecer o estado à saída de cada camada. A próxima prova substitui esse conhecimento pelo estado anterior e pelos ranks que o próprio target acaba de calcular. O controlo permanece R0. [Protocolo do plano causal](shadow-protocol.md)

Código `1cb4cba05932f3027fc499b8f2007354a5185069`, árvore `f9dcf7b784cf853cdb3a289f1140d5e9f80f2fc1`. ELF `b6fc408dd3c7c4d7b5d345c28388e6a2f6d23b0badc83f54a5459fe8e059dd55`. O diretório privado da campanha retém C55, o build e bibliotecas identificadas, o plano, o comando, stdout, stderr e as amostras. O GGUF original e o pack ficaram no NVMe interno. O ficheiro público permite repetir o avaliador sem modelo. [Comandos exatos do portátil](visit-commands.json) · [Inventário do arquivo privado](private-archive.json)

```sh
p=research/ready-experts/request_path/partition
python3 -IB "$p/visit_grade.py" --check "$p/evidence-visit-20261128-r01"
```
