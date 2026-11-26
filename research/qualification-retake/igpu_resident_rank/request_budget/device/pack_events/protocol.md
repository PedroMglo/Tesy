# Uma entrega de pack exposta ou escondida por cálculo

Pré-registo de uma fixture inteiramente sintética. A unidade verifica o método proposto para observar C291 no pedido P. Todos os tempos científicos usam um único relógio virtual com ticks inteiros de duração arbitrária. Quatro threads de trabalho distintas executam uma geração cada. Um coordenador avança o relógio por barreiras. A ordem entre workers no mesmo tick é livre. O tempo real de execução do Python só serve para diagnosticar a ferramenta.

## Contrato e população

Um DAG contém a autorização da rota no tick 0, quatro entregas em paralelo, um ramo independente de cálculo, o encontro das dependências e um consumidor de 2 ticks. Um registo mede apenas a duração determinada por esta construção. A quantidade de bytes e os tamanhos de operação são simbólicos. Os quatro slots começam vazios e terminam residentes. As quatro chaves lógicas, os slots, a geração, o papel de cada SET e o digest esperado do conteúdo distinguem as identidades. Há um preload para a quarta chave seguido de promoção na mesma geração e skip do duplicado. O produtor só consome bytes publicados. A execução real do consumidor confere os quatro conjuntos de três componentes.

Cada evento contém ordinal, tick, ator e tipo. Um evento de job inclui identidade (camada, expert, slot, geração). Os tipos representam autorização/reserva/fila/promoção/claim/skip, começo/fim do READ e dos três SET, publicação validada, remap com espera READY, disponibilidade do ramo de cálculo, consumidor e fim da fase. O cabeçalho liga o processo da fixture aos quatro TIDs observados, experimento, relógio e plano. O fecho inclui contagem, joins e digests. O revisor valida os eventos por identidade, ordem de controlo e dependências. Ordinais são usados apenas para desambiguar simultaneidade no relógio discreto. Um job físico conta uma vez.

## Casos fixados antes da execução

| Caso | Construção | Resultado exigido em ticks |
|---|---|---|
| hidden | READ 4 + três SET de 1 por worker. O ramo de cálculo dura 10. A publicação dos quatro jobs ocorre a 7. | Serviço 28 worker-ticks, união de serviço 7, espera READY 0, parede 12. Ao tornar as entregas instantâneas, a parede continua 12. Ganho exposto 0. |
| exposed | As mesmas quatro entregas. O ramo de cálculo dura 3. | Serviço 28, união 7, espera READY 4, parede 9. A parede com entregas instantâneas fica em 5. Ganho exposto 4. |
| unknown-fence | O lado host é igual ao caso exposed. O consumidor arranca a 9. O registo omite deliberadamente a origem da última dependência do consumidor, que pode ser visibilidade do SET no dispositivo ou outra dependência independente. | Serviço host 28, união 7, espera READY 4 e parede 11. Intervalo admissível de ganho líquido [0,6]. As duas explicações têm as mesmas marcas observáveis. Proibida uma estimativa pontual. |

O revisor calcula a parede pela cadeia mais longa do DAG de precedências, com o custo original e com READ/SET gratuitos. Preserva cálculo, consumidor e dependências independentes. O registo de WAIT é diagnóstico e não é um nó adicional com preço. Uma unidade fora do ramo CUDA sintético exige uma prova de visibilidade para dar um único valor. A janela desconhecida concede os dois extremos do contrato e deixa explícita a premissa de que acelerar entregas não atrasa os outros ramos. A ordem de quatro jobs atribuídos a workers diferentes não cria uma aresta entre eles.

Contraprovas mínimas: trocar uma geração na publicação, perder um componente ou a promoção passar a criar dois claims terá de invalidar a captura. Alterar a duração de cálculo em testes adicionais deverá mudar o ganho obtido do DAG, sem o deduzir do nome do caso. O runner escreve os eventos e a análise num diretório novo por execução, autentica ficheiros por SHA-256 e deixa uma falha terminal junto dos dados disponíveis se o verificador rejeitar. A saída pública pode omitir PID, TIDs e ordinais de eventos simultâneos.

Não haverá modelo, pesos reais, I/O de pack, CUDA, telemetria do anfitrião ou estimativa do tempo recuperável em P. A promoção é um teste de identidade e não tenta reproduzir o escalonador completo do manager. Uma aplicação a P dependeria da [observação no manager real](../packed_prefill/observation.md).
