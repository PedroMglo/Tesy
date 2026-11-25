# E/S do segundo pedido com o pack no NVMe

O cgroup C281/C291 submeteu **pelo menos 13 076 447 232 bytes de leitura ao NVMe interno** nos 7,955187 s entre o primeiro raciocínio e o primeiro conteúdo final de T2. O cliente recebeu o primeiro final em 18,104272 s. A sessão natural reproduziu os 78 tokens do primeiro pedido e os 47 do segundo; T2 reutilizou 2044 entradas e avaliou mais 153. O decode fez 5,351 tokens/s. [Protocolo](protocol.md) · [Recibo](receipt.json)

| Medida dentro da janela cliente | Mínimo | Máximo |
|---|---:|---:|
| Bytes de leitura submetidos pelo cgroup ao namespace NVMe | 13 076 447 232 | 13 354 106 880 |
| Bios de leitura debitados ao cgroup | 99 925 | 102 046 |
| Bytes de leitura concluídos no namespace inteiro, todos os cgroups | 13 095 149 568 | 13 363 355 648 |

O observador externo recolheu 988 amostras em 98,80 s e consumiu 0,367 s de CPU. Couberam 80 amostras inteiras na janela, com lacuna máxima conservadora de 100,7 ms. A partição Btrfs 259:3 pertence ao namespace 259:0. Os dois contadores têm âmbitos e momentos distintos. Os dados identificam o dispositivo destinatário das submissões do cgroup e deixam desconhecidos o ficheiro de origem e o emparelhamento dessas submissões com conclusões físicas na mesma janela. [Observador](probe.py) · [Revisor](grade.py)

| Relógio do produtor até à amostra 45 | Custo fixo assumido | Tempo que sobra dos 10 s | Máximo a 8 GB/s | Fração crítica do mínimo |
|---|---:|---:|---:|---:|
| Amostra a amostra | 9,564669 s | 435,331219 ms | 3 482 649 752 B | 26,632997% |
| Devolução do token ao grafo | 9,564667 s | 435,333219 ms | 3 482 665 752 B | 26,633119% |

Preservando o custo exterior aos 44 passos, se **mais de 26,634%** desse mínimo tiver de atravessar a mesma ligação no tempo que sobra, acelerar apenas a computação dos passos é insuficiente para os 10 s. Ambos os relógios conservam a classificação condicional dos dois P históricos; os limiares de 12,28% e 14,67% desses P usavam o contador do processo. A fração preservada e a sobreposição depois de uma intervenção continuam por medir. Houve um único P com observador nesta unidade. [Orçamento anterior](../README.md)

A preparação e a execução usaram o commit `3aefff6608b74dccf07e1c7ecb8e8a7744b469fb`. A C118 durou 60,180 s e terminou 0,048 s antes do arranque. O cgroup atingiu 15 778 426 880 B, com swap zero e STOP a 19,5 GiB. O servidor saiu com código zero, o serviço encerrou e a porta ficou livre. O lote privado contém a tentativa inicial do probe que detetou a diferença entre o dev_t do subvolume e o do mount, a verificação posterior do mount ID, a prova do sampler perante um serviço transitório, a C55, a preparação e a sessão. Uma revisão independente dos originais e uma reabertura do lote reproduziram integralmente a classificação. [Manifesto de 49 ficheiros e 1 814 054 B](archive-88.json)

Na checkout congelada, `ARCHIVE` designa a raiz de qualification-20261124-nvme-01. A repetição seguinte verifica o arquivo sem chamar o servidor.

```sh
u=research/qualification-retake/igpu_resident_rank/request_budget/device
python3 -IB research/qualification-retake/private_archive/verify.py "$ARCHIVE" "$u/archive-88.json"
```
