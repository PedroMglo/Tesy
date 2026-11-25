# Oportunidades de leitura observadas no manager C291

**GO para qualificar o observador de previsão no backend; efeito na conversa INCONCLUSIVE.** Um preditor de teste pôde publicar as suas sugestões no mesmo journal e relógio em que o manager classifica a procura autoritativa, reserva o slot e confirma a geração. Os dois processos CPU, OFF e ON, produziram exatamente os mesmos 157 quartetos, IDs físicos e contadores. Os bytes de cada matriz entregue foram conferidos. As sugestões do projetor de teste não entraram na fila de serviço. [Protocolo pré-dados](protocol.md) · [Resultado reproduzido](receipt.json)

| Na fixture | Resultado |
|---|---:|
| Posições de entrada em 5 + 148 + primeiro decode | 154 em sete tiles |
| Linhas oficiais, quatro ranks por linha | 154 na camada 1, três saídas selecionadas na 35 |
| Propostas que coincidiram com um ID da mesma linha | 574 / 628 |
| Procuras distintas classificadas no remap | 14 ausentes, 38 READY, 0 LOADING |
| Gerações ausentes com sugestão correspondente antes da callback | 11 / 14 |
| Serviço real dessas 11 gerações | 33 preads, 135 168 B pedidos e devolvidos, 4 224 B úteis e de SET |
| Serviço real do controlo inteiro | 42 preads, 172 032 B pedidos e devolvidos, 5 376 B úteis e de SET |
| Pedidos do preditor / bytes de leitura eliminados | 0 / 0 |

Na primeira tile apareceram dez faltas identificadas cedo nas duas camadas. Nas cinco tiles da chamada de 148, as seis chaves sugeridas e pedidas da camada 1 já estavam residentes em cada passagem. A última dessas tiles contribuiu com mais uma falta da camada 35 identificada cedo. No primeiro decode a sugestão da camada 1 foi retida propositadamente até ao fim do remap. Três dos quatro IDs estavam certos; nenhum recebeu crédito de antecedência. A mutação que rotula um residente como LOADING, altera uma geração ou atribui falsamente um claim também foi rejeitada. Para a fixture, a soma de spans de READ e SET dos workers foi 60 366 ns e a união desses spans no relógio de parede foi também 60 366 ns. O armazenamento era tmpfs. As percentagens de sinal e estes relógios da fixture não estimam a eficácia ou o custo no NVMe do 120B. [Revisor por geração](audit.py) · [Mutações](test_audit.py) · [Sinal medido à parte em C270](../tf32/README.md)

## Onde colocar a observação no C281

No C291 `c89c88b3`, `src/models/openai-moe.cpp:129–134` dá nome a `attn_post_norm` ao construir o grafo. Nessa linha o payload ainda será calculado. O mesmo ficheiro, linhas 119–123, recolhe apenas as saídas pedidas na última camada. A atribuição de linhas reproduz as duas vias de `llm_graph_input_out_ids::set_input` em `src/llama-graph.cpp:225–241`, com todas as linhas quando `n_outputs == ubatch.n_tokens` e a máscara nos outros casos. O hook em `llama-context.cpp` insere E31 a partir da ubatch efetiva, entre o registo da tile e `graph_compute`. Na fixture, o mesmo excerto foi compilado com um contexto mínimo. O revisor rejeita duplicação, travessia de retorno ou uso de uma posição sem output no destino 35. [Sobreposição privada de fonte](run.py) · [Emissor de eventos](lookahead.h)

Para uma primeira aquisição de diagnóstico no processo real, o `cb_eval` recebe primeiro o pedido de observação. Só na segunda chamada, após o sincronismo no scheduler de `ggml/src/ggml-backend.cpp:1674–1708`, a ativação pode ser lida. Aí começa a medição antes do GET/D2H quando necessário; a previsão fica disponível depois do GET, ajuste de gamma, projeção com o peso e bias do destino e seleção ordenada de quatro IDs. Publicar E33 sob o mutex nesse ponto. Cobrar a cópia, o projetor, a seleção e o sincronismo que o próprio observador introduziu. Uma variante assíncrona precisa guardar o ID imutável de call/tile/linha até à conclusão e proteger a vida do buffer; o contexto local da thread de um worker não identifica uma tile. O antigo C299 em `tools/expert_prediction_staging_cost.cpp:26–41` já distinguia o pedido de observação da leitura, mas usa outro operando. [Observador C299](../../../../tools/expert_prediction_staging_cost.cpp) · [Fonte do sinal desta hipótese](../protocol.md)

Quando a rota oficial chega, E27 liga a linha aos quatro experts do target. E34 é emitido logo após `expert_slot.find(e)` nas duas pesquisas reais da callback simples e da wave, sob o mutex que protege reserva e publicação. E11, E12 e E13 identificam slot, geração, fila e worker. E15/E16/E17 ligam a cada geração os READs, SETs e READY da entrega **por procura**. Os estados observados em E34 pertencem à procura efetiva. A espera até a GPU terminar o último consumo, uma leitura iniciada pela previsão e a hora a que essa leitura estaria pronta carecem de testemunha própria. A fixture exercitou uniwave CPU com componentes de 128 B, sem evicção. A via multiwave/preload, uma promoção LOADING real, o pack e a entrega CUDA não passaram por esta fixture. São necessários para a conclusão sobre o pedido. [Serviço de pack já qualificado separadamente](../../igpu_resident_rank/request_budget/device/pack_native/README.md)

**Gate seguinte.** Integrar o projetor calibrado e os tipos de evento na DSO de diagnóstico. Verificar no C292 OFF/ON logits finitos completos, top-k, KV, slots e IDs. A seguir, uma captura C281 OFF/ON pode medir a interseção com faltas e o prazo na conversa, depois de se verificarem proveniência, C55 e C118. A admissão de outra campanha referida no protocolo é técnica, dentro do mandato atribuído ao projeto. Demonstrar um ganho exige uma intervenção posterior que realmente emita a leitura cedo, com ablação de mesmo cálculo e sem envio, quatro workers, geração válida, os SET e o desperdício incluídos. O relógio de callbacks síncronos serve para diagnóstico. M3 e M4 conservam os estados previamente publicados.

## Reprodução sem modelo

A família congelada em `2a39c5c7` fechou em 3,668 s, incluindo compilação. O cgroup registou pico de 386 400 256 B, swap zero e zero OOM, dentro de 1 GiB. A família tem SHA-256 `7abb8c47c87044220482c31f8baebbf57796005f61295fb3e4fe3d131e848d08`. O PFJ contém 2 336 eventos selados e quatro workers terminados. O revisor relê os brutos de ambos os braços e autentica o vetor ordenado de posições, camadas, IDs e slots de OFF. O compacto tem SHA-256 `9062003a1677cfdc3151c5a149ebbf2a71f54e21190b4d92881217de6a636640`. [Revisor de reprodução](review.py)

```sh
python3 -IB "$UNIT/review.py" --family "$FAMILY" \
  --family-sha256 7abb8c47c87044220482c31f8baebbf57796005f61295fb3e4fe3d131e848d08 \
  --new-output-dir "$FRESH"
```
