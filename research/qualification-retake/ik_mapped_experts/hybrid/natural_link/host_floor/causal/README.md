# O banco causal de 10 GiB excede o orçamento antes do primeiro final

**TRACE_DERIVED · NO_GO para os dois braços sobre as rotas P97/P106 a 4,5 GB/s.** O LRU precisa de 56,116 GB da origem entre o início de T2 e o primeiro conteúdo final. Admitir só na segunda falta precisa de 58,217 GB. O custo mínimo do disco é de **12,470 e 12,937 s**, mesmo com zero custo de cálculo, retenção e coordenação e plena sobreposição com PCIe. O alvo é 10 s. O estado inicial de T2 provém das 14 885 reposições GPU de T1. O teste não altera a receita operacional nem qualifica a trajetória própria do servidor ik. [Protocolo em 606a5c72](protocol.md) · [Contagens e estados de fronteira](result.json)

| Recorte | Fills GPU | Hits RAM LRU / segunda falta | Origem GB LRU / segunda falta | Escritas para retenção GB LRU / segunda falta |
|---|---:|---:|---:|---:|
| T1 | 14 885 | 5 559 / 5 150 | 123,282 / 128,689 | 123,282 / 36,789 |
| T2 prefill | 3 238 | 1 379 / 1 332 | 24,574 / 25,196 | 24,574 / 10,232 |
| T2 decode completo | 3 987 | 1 556 / 1 435 | 32,136 / 33,735 | 32,136 / 15,837 |
| T2 até ao primeiro final | 7 079 | 2 834 / 2 675 | 56,116 / 58,217 | 56,116 / 25,645 |
| Dois turnos | 22 110 | 8 494 / 7 917 | 179,993 / 187,620 | 179,993 / 62,857 |

O decode de 47 saídas tem um orçamento de 7,833 s a 6 tok/s. Considerando apenas a obrigação mais longa de disco ou PCIe, os saldos desse recorte são 0,692 e 0,337 s para o restante trabalho. O H2D até à primeira peça custa pelo menos 5,849 s a 16 GB/s brutos em ambos os braços. As janelas sobrepõem-se e a linha de T1 paga também o estado inicial. Até ao primeiro final a admissão na segunda falta poupa 30,470 GB de escritas de retenção e acrescenta 2,102 GB de leitura da origem. Esse compromisso falha a proteção prévia do decode e do volume total. Os tempos são estimativas de serviço a partir das contagens lógicas.

O orçamento de payload acomoda 812 experts completos, 10 733 990 400 B. Acrescem 648 155 136 B de scratch e as tabelas de índices e recência. O máximo de chaves na fila de segunda oportunidade foi 812. Cada hit serve as três matrizes corretas à GPU. O trabalho conserva a ordem do planner e os 6 880 sítios das rotas. O piloto físico ik produziu 51 saídas em T2, a trajetória histórica usada aqui produziu 47. Para reabrir seria preciso baixar os bytes no primeiro final, colocar parte deles antes do pedido com custo contabilizado, elevar o débito útil acima de 5,612/5,822 GB/s, ou demonstrar outra trajetória. O melhor componente já medido no cliente continua a ser o pack do Tesy. [Melhor braço emparelhado](../../../../../packed_nvme_manifest/server_profile/conversation/ordens.md) · [Piloto físico ik](../../../../frontend/server/README.md)

O cálculo usou CPU e zero pesos, GPU ou pedidos. O motor nativo fixado no lote 155 foi recompilado no estudo de proveniência. Os originais e as cópias privadas de P97/P106 deram o mesmo recibo `f5d3c2c8306169db5267eceb32977f57bd1f83082dffafa938086ac861c516ca`. O teste por enumeração compara as duas políticas com uma máquina de listas independente em todos os prefixos de 972 casos. Reproduzir com `python3 -IB replay.py --p97 "$P97" --p106 "$P106" --planner "$PLAN_288" --new-output-dir "$NEW"`. [Simulador](replay.py) · [Testes](test_causal.py) · [Planner e autoridades dos dados](../../../cold_gate/backend_input/c110_graph/price/natural/README.md)
