# Cache LRU ik num único grupo GPU ao longo do pedido T2 nominal

Crivo offline anterior às contas. Condicionar o percurso às 7 012 linhas
ordenadas que o T2 Tesy partilha nas partes 97 e 106. Usar a reabertura de
natural_pages, o corte autenticado do cliente P97 e o inventário C283. Preservar
as duas chamadas 5+148, as cinco tiles 32+32+32+32+20 na segunda, a seleção
de output na camada 35, os 46 passos unitários seguintes e a ordem de ranks.
O primeiro final é a amostra 45 após a call 46. A sua marca de receção é do
cliente P97. Confirmar a origem do último conteúdo e o relógio de 47 tokens
em 46 avaliações pelo avaliador anterior; nunca transportar timestamps P97
para ik. Se a cobertura contrariar o esquema, preservar FAIL.

Fixar ik 7a5d90009b7ae55d3239cdd33244977c4eb10ff6, share=0, LRU, todas as 36 camadas
elegíveis no mesmo banco e sem prefetch GPU anterior à seleção. Comparar só
128 e 161 slots reais; a linha de guarda não armazena um expert. Executar o
planner C++ do próprio header, como o hook share=0, validar saídas contra uma
segunda representação lógica da recência, e confirmar elegibilidade por número
real de linhas. Cada falta transfere as 3 matrizes de 4 406 400 B, total
13 219 200 B; não contar biases, matrizes densas, metadados, tráfego de protocolo
ou estado do page cache no payload.

Frio é uma hipótese ilustrativa. Para qualquer estado inicial válido identificar
grupos seguramente ausentes por distância de reuso (K chaves distintas de
outros grupos/intervenientes desde o último toque). Uma sequência de K
inserções forçadas sem hits determina a ordem lógica completa, não os números
físicos dos slots. Até convergir, limitar a vantagem do estado inicial a K
hits se o prefixo incerto só pede chaves inéditas e distintas; validar que o
melhor prefixo é atingível inicializando o banco com as primeiras K procuras,
e comparar com vazio. Se falhar a prova usar apenas o piso do solver de
substituição ótima com entrada livre e um teto conservador. Reutilizar
cache_bound.minimum com pin por grupo também como controle inferior para
cada recorte, deixando o oráculo escolher de novo a entrada gratuitamente;
essa relaxação não descreve T1 ou a política ik.

Publicar fills/hits e payload por tile e por fase, incluindo os 44 passos
até à primeira peça final e os 46 até ao último token. A taxa necessária
até à primeira peça usa 10 s; para o decode usa 47/6 s. Se o piso sob qualquer
estado inicial exceder 16 000 000 000 B/s, o requisito é impossível nessa via
condicionada mesmo com toda a computação grátis. Para os outros pontos,
publicar o tempo consumido a essa taxa bruta, a margem para trabalho em série
e a taxa exigida. Nenhum PASS de produto ou universal para o fork. O teto de
capacidade PCIe da ligação já arquivada é otimista. A seleção de expert, o
estado do banco e os tempos da futura conversa ik serão dados desse target.
