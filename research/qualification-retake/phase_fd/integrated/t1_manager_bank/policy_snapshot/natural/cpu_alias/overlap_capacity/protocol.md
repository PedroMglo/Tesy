# Quanto dos 353 registos pode usar as páginas do primário CPU?

Pré-registo sobre a parte 63, T2 ON da família
`cb70c934dbbe0f1ca7452904718589b44fa906179208e7f95b0c934808d70a42`.
Manter as rotas, 25 camadas CPU e 11 CUDA, 40 slots por camada, parking,
waves, ordem das reservas e primário carry do replay. O seletor consulta
sempre as mesmas 353 tags de T1. Uma extensão muda apenas a disponibilidade
de bytes. O banco inclui as vítimas READY na ordem sob o mutex de T1.
Vítimas de CUDA guardadas em RAM não podem partilhar a alocação primária
de VRAM. O estudo de banco exclusivo mudou a composição ao promover e
expulsar durante T2. Aqui os pesos secundários permanecem imutáveis e
selados à entrada. [Replay da política](../../replay/README.md) ·
[Controle exclusivo](../../exclusive_bank/README.md) · [Prova da vista CPU](../mixed/README.md)

**Contabilidade.** Verificar o R0 físico por meio do replay que reproduziu
2 354 reservas. Fixar os dois planos de transporte já selados, o primário
antes de T2 e a seleção das últimas 353 vítimas distintas do seu próprio
prefixo. Para cada reserva verificar vítima, geração anterior, destino, tier
e origem. Publicar a interseção por camada na entrada/retorno de cada tile
e em cada retorno de decode, mais os mínimos e máximos por fase e camada
após cada reserva. Conservar separadas as interseções CPU e CUDA. No
candidato estas são posições lógicas prometidas. O último leitor, a instalação
e a publicação das páginas podem ocorrer mais tarde. Só cortes já drenados
admitem igualdade sob remapeamento competente. Nos outros pontos, o crédito
físico efetivo é desconhecido, entre zero e o valor que o respectivo estado
pronto permitiria; um leitor antigo pode manter uma versão adicional até ao
join. O crédito bruto máximo por duplicado CPU é um registo de 13 221 888 B.
Cobrar o padding relativamente ao primário denso, os quatro registos de
staging e o índice de 4 096 + 36×128×4 + 64×(K+4) B arredondado a 4 KiB (fórmula pinada de host_cache). As PTEs, o último
leitor e os buffers extra de handoff merecem uma coluna/condição própria.
Usar o pico cgroup e GPU da própria família comparada e os stops já definidos;
manter o orçamento fixo de K353 separado da margem da máquina.

**Teste causal de capacidade.** Fixar um único banco com crédito apenas de
bytes duplicados, mesmo orçamento histórico de K353 (4 720 263 168 B). Desde o
primeiro snapshot de T1, acumular as vítimas observadas em LRU, inicialmente
vazio. A cada RESERVE retirar o vínculo antigo do primário pronto; atualizar
a recência da vítima. A cada PUBLISH acrescentar o novo vínculo pronto.
Reter sempre o sufixo K353 do banco de referência; a parte mais antiga só
pode ocupar a folga paga pelo alias CPU sob esse orçamento. Gerir o excedente
por expulsão LRU imediata quando o custo ultrapassar o orçamento. A falta
transitória de capacidade para os próprios K353 é reportada explicitamente
(usar a folga conhecida do processo ou cobrar à parte); excluir nesse instante
qualquer extra. Não recuperar uma chave anteriormente descartada sem outra
oferta real. Congelar estas identidades antes do primeiro evento de T2. Ao
longo de T2 só permitir perder extras, por idade, antes de o seu backing ser
necessário para outro dono; nenhuma admissão retroativa, promoção nem nova
vítima de T2. Para o ramo de máximo potencial usar a interseção lógica após
reserva e conceder publicação imediata e liberação do último leitor. Registar
as primeiras faltas do disco cobertas em cada fase, a posição no pedido e o
total de admissões pagas poupadas na mesma agenda. Contar cada registo
distinto e cada admissão separadamente. Não atribuir segundos aos jobs ou ao
remap. Teste adversarial onde uma chave antiga descartada precede a folga e
onde duas gerações de uma mesma chave não compram dois registos.

**Limite externo.** Conceder ainda conhecimento do futuro só para calcular
um teto matemático. No corte anterior a T2, o banco extra só pode conter
vítimas oferecidas em T1 e ainda excluídas da seleção K353. Todas as extras
do tier CPU que já estejam no primário são inicialmente gratuitas no modelo
de páginas; no futuro podem consumir espaço. As restantes exigem uma janela
por chave; ordenar pela quantidade de jobs de disco que cada identidade
efetivamente serviria para obter o máximo sob essa restrição inicial, mesmo
concedendo retenção sem limites depois da entrada. Aplicar também o envelope
de pico físico R02 ON e a respetiva margem; não chamar garantidos os ganhos
que dependem de metadata, PTEs ou de timing não observados. Se esse teto
permitir vantagem mas a construção causal não a materializar, manter
INCONCLUSIVE sobre a realização física e identificar o dado mínimo.

Dois processos independentes, cada qual até 120 s e 768 MiB, outputs novos e
privados. Sem leitura de pesos, novo pedido ou trabalho GPU. Publicar
contagens por fronteira sem ids do prompt. O ensaio não admite M3/M4.
