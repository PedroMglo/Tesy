# Cadência do primeiro decode natural nominal do ClassLRU 288

Protocolo prospetivo escrito antes de conhecer qualquer preço FILE/ANON.
A questão é se passar de um drain por cada três SET de peso para um drain
por sítio reduz a espera de quem submete o grupo. O estudo anterior fixou
o sítio como uma execução do hook share=0 por camada. Fixar exclusivamente
a primeira avaliação de decode T2 (call 3, tile 1, 36 camadas em ordem);
sem timings de seleção ou varrimento por nº de fills. Inclui 92 fills, 276
cópias de 4 406 400 B, 36 GET de quatro IDs I32, seguidos de sync e 36 SET
do mapa lógico de 128 I32. A camada sem fill paga por estes dois movimentos.

Reabrir os ranks no P97 autenticado e o replay de slots de natural_runs
(duas leituras idênticas). Reconstruir o mapa ik do prefixo inicialmente vazio
antes de T1, estados antes/depois do sítio e os quatro slots em ordem oficial.
Os bytes provêm de um shmem determinístico FILE read-only, residente,
sem registo CUDA. Preaquecer e validar mincore/endereço, assinatura de cada
origem e zero I/O de blocos; ANON com os mesmos bytes/endereço módulo página
é o controlo do tipo de fonte. A fonte de dimensão reduzida é reutilizada
entre camadas e repetições. A projeção do destino para quatro slots conserva
o binding dos quatro selecionados e a identidade lógica da chave no plano.
O alvo testa a cadência; não reproduz a distância entre todos os 288 slots
nem as faltas de página ou o trabalho de FFN do fork.

Comparação emparelhada com a mesma sequência role-major gate, up, down, o
mesmo mapa transferido e os mesmos bytes. A cada três SET de pesos, no modo
TRIPLET, drenar o stream; GROUP apenas prepara tudo. Ambos fazem uma leitura
de IDs seguida do sync anterior ao plano, enviam o mapa no fim e drenam para
medir e verificar o serviço completo. Assim TRIPLET mede a granularidade
de uma espera a cada 3 SET, mesmo quando os três SET abrangem papéis de
experts diferentes. Verificar todos os 36 sítios incluindo o caso sem fill;
reconciliar chegadas dos IDs, plano, pesos, mapa, readback dos quatro ranks,
destino errado/valor sentinela e cleanup. A obtenção nativa de ClassLRU e
a aritmética de FFN ficam externas se o cliente usar o plano arquivado;
o custo de verificar/aplicar o resultado da procura será cobrado nos dois
braços. Nenhuma dependência de um consumidor real pode ser simulada com sleep.

Medir na mesma origem monotónica as regiões disjuntas GET+sync, aplicação do
plano, chamadas de SET dos pesos, esperas intermédias explícitas, SET do mapa
e drain terminal. Conservar parede total do sítio e CPU da thread; imputar
qualquer resíduo de instrumentação em coluna própria. O retorno de uma API
async pode pagar staging síncrono no driver. Se o tempo aliviar apenas no
drain intermédio, mas reaparecer no SET de páginas normais, ou no drain
final, a hipótese de reduzir a parede completa é refutada nesse par.
Predição direcional primária: soma de parede dos 36 sítios GROUP menor que
TRIPLET para FILE nos dois processos. Sinal não repetido é INCONCLUSIVE; dois
sinais contrários fecham essa hipótese na fixture. Separar sinal de ANON e
sítio vazio. Sem converter resultado em latência de produto.

Duas ordens invertidas em processos novos sob política, C55/C118/E2, zero
swap, mesma RT/DSO e CUDART que o ensaio unitário. Em cada processo quatro
travessias medidas: FILE-TRIPLET, FILE-GROUP, ANON-TRIPLET, ANON-GROUP,
ordem inversa no segundo. Cada travessia envia 1 216 166 400 B de pesos
mais 18 432 B de mapas, e recebe 576 B de IDs. Oito travessias até
9 729 331 200 B de pesos. Preceder de uma travessia de exatidão por processo
(em modos opostos FILE/GROUP e ANON/TRIPLET, verificação integral de cada
slab comprometida) cobrada separadamente; máximo de dez travessias e
12 161 664 000 B H2D de pesos. Os poisons/leituras de controlo ficam fora
da janela, autenticados e discriminados; stop no primeiro mismatch. Limites
prospectivos: 60 s por filho, família 300 s incluindo C118, até 2 GiB de
cgroup (stop 1,5 GiB), GPU <1536 MiB usada segundo a política; 64 MiB de
raw. Preparador e fixture de contraprova sem modelo primeiro; build e reserva
física da janela surgem em etapas próprias. Nenhum preço de hardware nesta etapa.
