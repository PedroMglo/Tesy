# Quatro entregas antecipadas entre os FFN das camadas CPU 0 e 1

**MEDIDO — GO para a próxima fixture emparelhada.** A antecipação reduziu o tempo entre a ativação disponível na camada 0 e o fim do último worker em **14,135 ms (2,52%)** no primeiro par e **3,354 ms (0,61%)** na ordem inversa. São dois pares no mesmo portátil, sobre as posições 0–31 do prefill C292. A sessão M3/M4 continua por qualificar. [Protocolo](protocol.md) · [Resultados e SHA](result.json)

| Execução física | Ordem | Até ao join, ms | Projetor, ms | Espera remap L0, ms | Espera remap L1, ms | Cleanup, ms |
|---|---|---:|---:|---:|---:|---:|
| Exatidão | OFF | 582,698 | 0,499 | 289,376 | 220,861 | 3,976 |
| Exatidão | ON | 562,075 | 0,516 | 294,497 | 200,693 | 2,685 |
| Par 1 | OFF | 560,463 | 0,494 | 288,901 | 207,327 | 4,688 |
| Par 1 | ON | 546,328 | 0,494 | 275,627 | 206,532 | 2,652 |
| Par 2 | ON | 545,198 | 0,494 | 279,645 | 201,940 | 3,107 |
| Par 2 | OFF | 548,552 | 0,490 | 275,938 | 204,337 | 3,195 |

O mesmo projetor BLAS produziu os 128 IDs arquivados e ofereceu os experts 42, 19, 56 e 113. Só o ON enfileirou leituras antecipadas. Cada execução devolveu **1 652 736 000 B em 125 preads** ao FD O_DIRECT do pack integral no NVMe. O OFF fez 66 leituras de procura ou preload na camada 0 e 59 na camada 1. O ON fez 66 e 55, mais quatro especulativas pertencentes à camada 1. As quatro foram consumidas uma vez, com zero desperdício e zero releitura. Houve 375 SET e 1 652 400 000 B copiados em cada braço. O contador Linux do dispositivo no cgroup acumulou 9 916 416 000 B de leitura nos seis processos. O conjunto C292 de prefill CPU estudado anteriormente incluía 141 ofertas erradas em 562. O acerto 4/4 desta tile limita a extrapolação. [Worker e limites de escopo](../README.md) · [População C292](../../numeric/windows/README.md)

A prova de exatidão conferiu em cada braço os 375 SHA das slabs contra o índice C290 e os bytes depois de cada SET. Cada FFN produziu os mesmos **92 160 F32 finitos** que o C270; os dois grafos mantiveram cada um 24 MUL_MAT_ID, 24 ADD_ID, oito waves, quatro ativas, 128 ranks, máscara, slot e geração correspondentes. Os primários começaram vazios com 40 slots por camada. O manager serviu 89 preloads e as 125 publicações em cada processo. Nas quatro medições, 81, 79, 84 e 82 itens de fila foram promoções de um preload LOADING, todos reconciliados em ordem FIFO até ao pop e à publicação única da geração. [Grafo e oráculo](graph.inc) · [Auditoria independente](review.py)

Nos dois ON de timing, a união das leituras antecipadas dentro do FFN0 foi **17,514 e 17,691 ms**. Dessas janelas, 11,619 e 11,706 ms decorreram durante o remap da própria camada 0. Restaram 5,895 e 5,985 ms fora do remap; os kernels individuais da CPU não foram cronometrados. Ao terminar o FFN0, zero e um dos quatro registos estavam READY. Os restantes chegaram antes de serem consumidos. O ganho de parede também inclui variação da camada 0, das cópias e do cleanup. No segundo par o tempo de espera total de remap até aumentou 1,310 ms enquanto a travessia terminou 3,354 ms mais cedo. [Medição](native.cpp) · [Arquivo físico](../../../../../private_archive/part-120.json)

Cada braço usou uma única fila com quatro workers, incluindo a procura e os preloads das duas camadas, e as mesmas entradas legítimas de FFN. O grafo 1 recebeu a ativação e o routing arquivados só após conferir o FFN0. Este recorte omite a atenção e o residual seguintes e o cálculo autoritativo do router; inclui a validação do FFN0 e do FFN1, a cópia das saídas e o join. O O_DIRECT contorna a page cache de dados. O estado interno do controlador NVMe é desconhecido. A duração da família foi 64,752 s incluindo C118 de 61 amostras. Pico de cgroup de 1 342 386 176 B, limite de 4 GiB, swap zero; sem GPU nem carregamento do modelo inteiro.

**Proveniência e falhas.** O protocolo ficou em `a10f6fb8` antes do ensaio e o executável de R03 em `7cd4b4c0`. As C55 R01/R02 não admitiram execução. A família R01 falhou antes do C118 ao abrir o destino do inventário. R02 parou após o primeiro OFF de exatidão porque o primeiro auditor tratava uma promoção válida como enqueue duplicado. A identidade que provocou o erro em R02 ficou por observar. O aditamento preserva a distinção entre promoção, segunda claim e publicação. O revisor voltou a obter o mesmo SHA a partir do original e da cópia arquivada. [Preparação e R02](../../../../../private_archive/part-119.json) · [Correção prévia à R03](queue-addendum.md)

A reprodução seguinte volta a autenticar o recibo e os seis braços guardados. A CLI de construção usa a checkout C305, os ELF CPU/base do C269 e o OpenBLAS congelados. A preparação usa os manifestos das partes 23 e 116, o índice do pack C291 e os coeficientes qualificados. Os comandos físicos e respetivos limites estão no supervisor. [Construção](build.py) · [Preparação](prepare.py) · [Supervisor](profile.py)

```sh
python3 -IB "$STUDY/review.py" --raw "$PART120/tesy-real-tile-family-20261125-r03" \
  --sha256 45df96bee9a2204c53168ecdb521e993723c39b08a56e3d0cc280965f6b3e893 \
  --new-output-dir "$NOVO"
```
