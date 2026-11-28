# Paga-se a promoção de 48 até à última publicação da wave?

Protocolo prospetivo de 28 de novembro, base direta do PR #52 em f15b287e48b125efdae1a1f2db8b36dfe5fbc94a, árvore 81b33ed9d8bc73141e88caa7d8dc54126cd04889. Origin/main em 293f5b184da9439771cce361cd33fc4068d749f4. A pergunta é se o ganho local do par chega ao consumidor quando os outros experts competem pelos quatro workers. Mantêm-se R0 slots40-persistent, ub32, contexto 8192, M3 PARTIAL e M4 NOT_MET.

P97 e P106 identificaram a mesma FIFO pendente e o mesmo routing do target na chamada 2, tile 1, camada CPU1, wave 0. Reconciliar a fila, as gerações, as reservas, os 16 experts procurados, as 32 linhas top-4 e a barreira original. A wave exigiu sete publicações novas, sem serviço alheio já iniciado na entrada. Confirmar que o primeiro claim acontece após o início da espera, com as sete reservas já na fila, e que a barreira termina depois da última publicação. Determinar os nove hits e os slots físicos. Guardar as identidades e os dois recibos, sem cruzar relógios entre journals.

## Graus de liberdade

Cada braço tem quatro workers persistentes, os mesmos sete registos O_DIRECT no NVMe interno, um buffer alinhado por worker e uma janela extra para o segundo registo, disponível em todos. Cada matriz MXFP4 é instalada com o SET síncrono do GGML C269 na respetiva geração e slot de um tensor CPU com 40 slots. Os nove hits são instalados antes da experiência. Invalidar os sete destinos antes de cada braço. Publicar individualmente só após os três SETs. O consumidor espera por todas as 16 identidades e aplica o remap de 32×4 às rotas capturadas. O relógio principal vai da libertação dos workers, com as reservas conhecidas, ao retorno do consumidor com o remap. Medir também o drain da equipa, os eventos de cada geração, a disponibilidade do par e dos dois intervenientes e a última publicação. Os hashes e a preparação ficam fora. Este cliente interno termina antes das multiplicações e da redução do FFN.

| Braço | Trabalho |
|---|---|
| F | Pedidos individuais na FIFO original 47, 3, 10, 48, 82, 44, 98 |
| P | Promover 48 a seguir a 47 e manter um pedido por registo, com a mesma fila partilhada |
| S | Mesma promoção, reservar o par num só worker e fazer duas leituras sucessivas; publicar cada registo após os seus SETs |
| M | Mesma promoção e worker, um preadv para os dois registos com o padding pago, seguido dos SETs e da publicação individual |

Registar a ordem de aceitação sob o mutex, os READ, os três SETs, a publicação, a propriedade do buffer e a barreira num único relógio monotónico. A ordem de conclusão dos workers pode variar. Fechar na primeira falha de fonte, parcimónia de bytes, geração, remap, recursos ou exatidão. Num controlo de falha de geração, o consumidor tem de recusar um slot certo com geração errada. Conferir os 48 hashes de matrizes dos 16 experts e os 128 IDs físicos por braço, antes de admitir timing e após cada repetição. O layout, os experts, as cópias e os hits mantêm-se em todos os braços. O pedido conjunto paga 36 864 B adicionais por par.

## Saída

Um quarteto de paridade antes de dois blocos com cinco quartetos, F/P/S/M e ordem inversa. Publicar todos os pares. GO no serviço local para M exige ganho mediano de M sobre F, P e S na barreira e sobre F no drain, em ambos os blocos. Perder para F na barreira em ambos fecha M nesta wave. Os demais resultados são INCONCLUSIVE. Aplicar autonomamente o mesmo teste de sinal P/F para saber se uma permuta de pedidos individuais explica o ganho. Um custo positivo local abre apenas comparação no pedido com tráfego e trabalho idênticos. Contrastar o ganho por comando com 6,950087 ms, condição média necessária do limite P106 para que a coalescência isolada chegue ao primeiro final. Uma única wave não representa esse preço médio.

C55 recente, 60 s de inventário vivo do portátil, AC/performance, stop térmico e monitor do scope. Cap 1 GiB, parar a 896 MiB, swap zero, ≤180 s de execução, ≤4,5 GiB de pedidos ao pack e ≤8 MiB por ficheiro de raw, sem pesos duplicados em disco. Receitas e binários selados antes das leituras, diretório exclusivo, FAIL preservado. Energia total desconhecida sem medidor. Sem forward do modelo ou trabalho na GPU. A abordagem herda o mecanismo de despacho da fixture física do par e usa os tensores e a cópia CPU do backend do Tesy.
