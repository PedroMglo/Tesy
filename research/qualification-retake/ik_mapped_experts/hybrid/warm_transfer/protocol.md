# Preço de três SET do ik a partir de páginas residentes

Antes dos resultados. O antecedente 20B comparou seis tensores preparados
incluindo os biases. Esta fronteira usa o ik 7a5d9000, a mesma libggml SM89,
o backend CUDA0 e a mesma stream que o hook share=0. Requer primeiro a
qualificação física RESIDENT/BANK9/BANK7 da pequena fixture, recibo e DSOs
selados, checkout limpa e os gates C55/C118/E2. Um único fill isolado de
um expert exige três ggml_backend_tensor_set_async, gate, up e down, de
4 406 400 B cada, seguidos de ggml_backend_synchronize. A região do destino
é um slot interior de cada tensor MXFP4 [2880,2880,3]. A linha de guarda e
os outros slots não recebem payload do ensaio. Não agrupar experts vizinhos:
o hook só coalesce quando os dois índices de expert e slot são consecutivos;
a frequência dessa condição na conversa do ik é desconhecida.

Gerar conteúdo não constante e distinto por papel num memfd selado contra
escrita, redução e aumento. Reabrir o mesmo inode O_RDONLY, fazer mmap
read-only, usar em cada slab o offset módulo 4096 da matriz L0/e0 do
inventário C283 autenticado. O controlo copia uma imagem byte-idêntica para
páginas anónimas normais, também read-only no momento do ensaio, com os
mesmos offsets. Nenhum peso, registo de memória host ou fonte de dados no NVMe.
Aquecer e verificar as páginas via mincore por intervalo tanto antes como
depois de cada medição. Conferir VMA, contexto, ausência de registo CUDA da
origem, tamanho e stride dos pesos e o destino efetivo de cada chamada CUDA.
Qualquer apoio interno de staging do driver permanece no preço.

Dois processos novos nas ordens de início FILE/ANON e ANON/FILE. Em cada
processo uma passagem de exatidão por modo com leitura integral independente
de volta. Depois, cinco pares alternados, com o sentido do primeiro par
invertido entre processos. Antes de cada repetição envenenar fora do relógio
as três janelas de readback de cada destino (64 B no início/meio/fim), drenar
o poison, verificar após o drain da transferência que essas nove janelas
mudaram para os bytes esperados. Proteção contra transferir uma fonte/papel
errado ou aceitar bytes deixados pela repetição anterior. Publicar todas
as repetições e a mediana por modo e por par; registar sem subtração tempos
CLOCK_MONOTONIC e CPU da thread e do processo, rusage, bytes e cobertura.
O relógio principal abre antes do primeiro SET e fecha só depois da
sincronização. A medição separa o tempo de submissão do restante drain.

O máximo é 24 fills, 317 260 800 B H2D dos pesos, mais poison/readbacks
diagnósticos exteriores. Até 30 s por filho, 2 GiB cgroup sem swap (stop
preventivo 1,5 GiB), <1536 MiB VRAM observada e 64 MiB de ficheiros na
família. A preparação, o warmup, envenenamento, mincore, verificação, entrada
e saída do processo têm âmbito separado. Falhar se faltar uma página, se
for observada fonte registada ou destino diferente, se os contadores/bytes
ou gates não reconciliarem. Conservar cada falha em destino único. A
telemetria reaproveita o supervisor anterior em três barreiras, sem amostrar
em cada SET.

Contrastar a taxa útil concluída de FILE em cada processo com 10,483 e
7,942 GB/s, necessários para os dois relógios de ClassLRU 161 na trajetória
Tesy. Mostrar também B/s agregados por soma de bytes/parede. Se falhar um
corte a mediana da fixture, a composição fica abaixo desse corte no cenário
de fills isolados àquela taxa. Um PASS é um preço possível para fonte quente.
A distribuição dos fills, aritmética e custos críticos reais do ik, cache
de disco file-backed sob pressão, source faults e concorrência externa
continuam fora da fixture. O memfd é um ficheiro shmem residente, com
contabilidade de residência e readahead distintas de um GGUF no Btrfs.
