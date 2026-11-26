# Uma observação C291 para identificar o serviço exposto

O dado em falta é o **tempo máximo do prefill que pode desaparecer ao modificar apenas as leituras do pack e a entrega dos seus três componentes**. O número de faltas e a soma dos tempos dos quatro workers não identificam esse ganho. A fonte C291 já reserva e protege slots, reclassifica um preload pendente como demanda e inicia trabalho da wave seguinte antes de consumir a atual. Um mesmo serviço físico pode satisfazer duas entradas de fila.

### Registo mínimo de um pedido

Usar uma sessão natural de dois turnos com a mesma template, tokenizer, histórico, pack, geometria, DSOs e contrato de saída. Armar o registo antes de T2. Registar os dois cortes de prefill em detalhe e a conclusão do trabalho que atravessa o segundo corte. Conservar as marcas que ligam os 46 passos seguintes às posições, saídas e ao primeiro conteúdo final do cliente. Os campos identificadores permanecem no arquivo privado. Para uma estimativa de custo do observador ou de ganho de desempenho será preciso um controlo contemporâneo.

| Registo | Campos e significado |
|---|---|
| Cabeçalho e cortes | Versão, PID/processo, relógio monotónico e resolução, capacidades, digests do executável, DSOs, modelo, índice e pack, identidade do FD e namespace, modo direto e alinhamento, quatro workers e identificação do cgroup. Em ENTER/RETURN de cada chamada guardar posição, contagem, máscara de outputs e estado por camada à entrada/saída (occupant, geração, READY/LOADING, claim, pins e fila pendente). |
| Rota e disponibilidade | Call, tile, camada, wave, posição, rank lógico e expert, máscara de parking e slot físico. O instante de disponibilidade da rota autoriza um trabalho dependente. Guardar, sob mutex, demanda, reserva, promoção de preload, dispatch, skip de duplicado e publicação com expert, slot, geração, origem, destino e um ordinal de evento. |
| Entrega | Para a geração reclamada, início/fim do pread, TID, offset e extensão alinhados do índice, bytes lógicos, pedidos e devolvidos, errno. Três pares início/fim de SET com papel gate/down/up, backend, destino e tamanho. Conservar retorno e visibilidade para o consumidor separadamente quando o backend submete trabalho assíncrono. |
| Dependências e relógio de parede | Início/fim do remap e digest dos pins. Marcas dos waits com predicado (slot livre ou geração READY), wake, último consumidor, liberação e sincronização efetivamente existentes. Preservar intervalos do grafo que não podem sobrepor-se ao serviço. Relacionar chamadas, produtor e transporte pelo relógio ou por limites de sincronização documentados. Conservar as janelas da telemetria do dispositivo sem as converter em timestamps de eventos do manager. |
| Integridade | Quantidade de registos tentados/salvos, overflow, erros, identidade do mesmo PID, estado das filas nos cortes e após join dos quatro workers. Registo de memória limitado, sem descarga obrigatória por evento. O ensaio que fornecer esta observação terá de congelar previamente o formato binário, os limites e o custo admitido. |

Conferir os 2044 tokens de histórico reutilizados, chamadas 5 e 148 (tiles 32/32/32/32/20 na segunda), máscara de outputs e poda por camada, ranks, correção de estacionamento, contabilidade das gerações e efeitos de preloads que cruzam retornos. Cada publicação válida deve referir um claim da geração correta, leitura completa e três entregas válidas. Conferir os 78/47 IDs amostrados, hashes dos canais e o instante do primeiro final contra os validadores do cliente original. Identidades de threads e ordens de conclusão pertencem à sessão observada. Trabalho anterior pendente, marca perdida, visibilidade assíncrona incerta ou diferença de rota alargam o limite ou deixam a atribuição indeterminada.

### Da observação à decisão

Construir o grafo de precedências da sessão com disponibilidade da rota, dependências reais da camada, publicação/consumo e proteção contra overwrite. Para um teto de ganho, conceder custo zero às entregas alvo e remover todas as esperas que poderiam desaparecer com elas. Para uma agenda livre de reorder, podem omitir-se dependências incertas para obter um limite mais otimista. A ordem acidental dos quatro workers no traço é uma dessas dependências se a intervenção puder trocar a ordem dos jobs. Contar só trabalho exterior comprovadamente indispensável às mesmas saídas, com preços explicitamente assumidos estáveis. A duração mínima L demonstrada por este grafo dá **U ≤ p − L**. Trabalho paralelo entra pelo comprimento do caminho crítico, sem somar leituras e espera do consumidor no mesmo intervalo.

Para admitir um teste basta apresentar por separado uma agenda causal completa que respeite capacidade, pins e workers, pague entregas/novos custos e atinja o ganho requerido sob as mesmas premissas de preço. Revalidar o carry antes de conservar um preço anterior de decode. Se uma observação de host só der os retornos dos SET CUDA, conservar o intervalo de dependência como desconhecido até à fence real. Uma soma de WAIT ou um calendário que conhece as rotas futuras não satisfazem o predicado. [Critério quantitativo e exemplo a 6 tok/s](README.md)

### Ponto de instrumentação

No backend C291, revisão `c89c88b342054223e3f27a17fbfd0954803147ac`, `src/llama-moe-stream.cpp` contém `worker_loop` (linhas 320–376), `reserve_slot_locked` (411–424), a reserva e a condição de espera do remap (543–565), e demanda, promoção e preload por wave (656–724). `src/c291-expert-store.h` define a leitura do registo. A publicação ocorre sob o mutex depois de revalidar slot, geração, claim e sucesso do serviço. A unidade é só uma proposta de observação nestes pontos. [Aquisição natural e seleção do pack](../../../../packed_nvme_manifest/server_profile/conversation/README.md)

| Fonte no pin C291 | SHA-256 |
|---|---|
| `src/llama-moe-stream.cpp` | `044d8879be19e5c22331a29bf7a273307756de10675b1341ee9d7077e2dabc62` |
| `src/llama-moe-stream.h` | `387c9f6ff17dbf74cf2ff4e280854760a1cfad39cabe0a245312564a7763ced4` |
| `src/c291-expert-store.h` | `3f2d786a2188f178655a8ed708e9c3a972b4919318aa4224c839ca13d83961a1` |
