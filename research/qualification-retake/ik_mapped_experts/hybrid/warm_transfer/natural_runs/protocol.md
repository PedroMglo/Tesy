# Quantos SET contíguos exige ClassLRU no replay nominal?

Análise sem dispositivo. Conservar o estado ik inicialmente vazio antes de T1,
um grupo share=0, capacidades 161 e 288, as 74 278 linhas T1 e 7 012 T2
seladas das partes 97/106. A fronteira do primeiro conteúdo final inclui até
à call 46 da trajetória T2. O commit 7a5d9000 define a ordem dos experts
únicos, faltas e vítimas. O replay anterior de 161 verificou os censos por
sítio contra o planner nativo. Os censos, por si, deixam em aberto os IDs
físicos dos slots.

Antes de calcular, fixar a regra de identificação: seguir a lista nativa
de slots vazios e a herança do slot da vítima numa falta; a promoção de um
hit preserva o seu índice. Contrastar em cada sítio duas representações,
por chave e por fila de índices físicos, incluindo todos os pares
(expert,slot) na ordem de emissão, os hits/fills/evictions, o relógio e
os estados finais. Para 161 e 288 exigir o mesmo digest dos censos que no
estudo two_steps. Reportar IDs de slots como dedução do pin com início
vazio, sem alegar uma captura de slots do ik no pedido real. Se os IDs
ou a ordem não ficarem demonstrados, só publicar o teto de um SET por
slab e o piso por cadeias de IDs de expert consecutivos no mesmo sítio.

Aplicar por sítio e por papel o laço exato do hook: estender o run só
se o próximo expert e o próximo slot forem ambos o anterior +1.
Uma falta envia três slabs de 4 406 400 B. Conservar a separação de
camada, tile, chamada e papel mesmo que haja contiguidade por acaso.
Publicar histogramas por comprimento (por papel), somas de SET e bytes
isolados/agrupados, sítios sem faltas e GET/sync de IDs e SET do mapa
previstos na fonte. Reportar separadamente T1 prefill/decode, T2 call
de 5 e cada tile de 148, primeiro decode, decode completo, primeira
peça e total. Guardar as linhas por sítio em saída privada selada e os
totais pequenos no Git. Os custos medidos em warm_transfer existem
somente para um fill isolado e drain explícito. Não ajustar latências
de produto nem imputar clocks ou tráfego físico.

Duas reproduções independentes com os originais e a cópia selada. As
mutações sem pesos cobrem contiguidade só na origem, só no destino,
reinício entre sítios e a recuperação do slot físico da vítima. Sem
compiladores, GPU, modelo, alteração do ik ou novas capacidades.
