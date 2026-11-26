# Quanto tempo segue waves completamente vazias?

**HEADROOM_ONLY para estudar a CPU numa fixture.** Nos dois traces do pedido nominal, 739 das 925 waves CPU da chamada de 148 não receberam qualquer rank ou reserva. O intervalo da saída dessas waves ao próximo callback ou retorno soma 1,233 s no P97 e 1,341 s no P106. Para pagar o que faltava no limite mais favorável da parte 198 seria necessário retirar 18,2% e 41,8% desse tempo. Com os preços seriais do mesmo processo, as frações sobem para 45,5% e 66,9%. A atribuição inclui inclusive o trabalho da camada seguinte quando a wave vazia termina uma camada. [Protocolo](empty-protocol.md) · [Contagens, intervalos e cenários](empty-result.json)

| Call / destino | Waves ativas / vazias | Ranks ativos / reservas | Lacunas após as ativas P97 / P106 | Após as vazias P97 / P106 |
|---|---:|---:|---:|---:|
| 5 · CPU | 25 / 0 | 500 / 40 | 0,136 / 0,150 s | 0 / 0 s |
| 5 · CUDA | 10 / 0 | 200 / 11 | 0,012 / 0,013 s | 0 / 0 s |
| 148 · CPU | 186 / 739 | 14 800 / 768 | 1,966 / 2,166 s | 1,233 / 1,341 s |
| 148 · CUDA | 88 / 283 | 5 924 / 444 | 0,140 / 0,141 s | 0,212 / 0,224 s |

O verificador atribuiu cada rank de cada posição à única wave que serviu o expert naquela tile e camada. As waves vazias formam sufixos e emitiram zero reservas em ambos os destinos. As lacunas e o tempo anterior ao primeiro callback recompõem o complemento já medido em cada chamada. O próprio remap já recebeu duração zero na parte 198. Esta análise concede todo o tempo entre callbacks ao candidato antes de medir que operações consegue evitar. [Código](empty.py) · [Reconciliação dos dois relógios](outside.md)

**NO_GO para o caminho retrospetivo específico com a CPU como única mudança adicional e o mesmo limite de exposição.** Mesmo concedendo a remoção de todas as suas lacunas CPU vazias, ainda faltam 26,0 e 254,2 ms para os 10 s. Ao conceder as de CUDA também, esse caminho cabe no primeiro trace e continua 30,0 ms aquém no segundo. O limite sobre todas as listas e agendas é mais permissivo. Dar todo o crédito à CPU deixa um piso de 9,328 e 9,556 s até com os preços dos passos seriais do mesmo processo. Esse piso pode ser atingível por nenhuma agenda. Uma futura medição do caminho útil nas waves também terá de pagar a coordenação, testar os dois turnos e qualificar o decode.

O backend C291 emite ID físico −1 para cada rank estacionado na CPU com a opção R0. O operador MMID de C269 escreve +0 nas suas saídas estacionadas e ainda converte ativações e sincroniza threads. O grafo aplica bias de down com o ID lógico, multiplica pela máscara e soma ao acumulador. Uma fixture deve testar o efeito no sinal de zero e manter serviço, máscaras, slots e ordem de redução. A extensão a CUDA exige estudar o caminho de parking próprio do dispositivo. [Fonte do grafo e manager](../../../../../../../../../../../../phase_fd/integrated/t1_router_window/source.md) · [Trabalho residente de CPU já medido](../../../../../../../../../../../../phase_fd/integrated/cpu_residual/resident_team/README.md)

As duas execuções na árvore limpa de `51f1e6aae9cf9448b194d5daef2f75ab87110183` duraram 2,896 e 2,906 s, com picos de 103,1 e 101,5 MiB, zero swap, GPU e novos pedidos. O resultado tem SHA-256 `254cd2134868c9184d84f22820b8d5d3f290657d4427a0049dc76cf9f96780b8`. Reproduzir com `empty.py` e os argumentos archive, capture, verified e plan do [comando anterior](joint.md), este commit e um novo destino. [Recibo de quatro ficheiros, 13 110 B](../../../../../../../../../../../../private_archive/part-199.json)
