# Referência independente para os turnos Aster

**MEDIDO · PASS_DETACHED_RENDER_ONLY.** As duas bibliotecas C++ de produção processaram as mensagens C133 em memória, sem abrir o GGUF. O stock original ignorou a data pedida nos dois turnos e usou a data do sistema. A diferença de bytes entre as duas bibliotecas ficou confinada à data na mensagem de sistema. O digest do template original é `a4c9919cbbd4acdd51ccffe22da049264b1b73e59055fa58811a99efbd7c8146`. [Protocolo](protocol.md) · [Recibo sanitizado](attempt-01/receipt.json)

| Turno e histórico | Bytes C269 | SHA-256 C269 / stock com data vinculada | Stock original, mesmo kwarg |
|---|---:|---|---|
| Primeiro pedido | 555 | `a07cf6a4695b…` | `a70a0ca18ea0…` |
| Segundo, com a resposta final histórica | 2029 | `76ae0367d000…` | `6af4d65aced5…` |

Numa cópia de Jinja destacada, a expressão de relógio foi substituída pelo valor de `tesy_template_date`. O novo digest é `0ccef2b31697ba30f891ed18cfc1203b8603f26fc4233faa98839c674819b9eb`. O stock com esta Jinja produziu exatamente os bytes de C269 em ambas as datas pré-registadas e em ambos os turnos. O cliente C269 está ligado à libllama-common `cc5a0f0b264b…` e o stock à `7cf9543328e8…`. O manifesto C133 de entrada é `0a96782a6be1…`. As compilações demoraram 0,916 e 0,947 s, com picos de RSS de 266,6 e 301,5 MiB respetivamente. [Manifesto das entradas](../two_turn_evidence_r1/manifest.json)

### Aplicação aos ensaios emparelhados

1. **Chat e produto.** Registar o SHA do template efetivamente usado em cada braço. Congelar o ficheiro local no stock e a data em ambos. Para as mensagens exatas de cada turno, comparar a saída de `/apply-template`, depois o array completo de `/tokenize` (`add_special=false`, `parse_special=true`) com as entradas originais. O vetor esperado tem 121 IDs no primeiro e 435 no segundo. Publicar contagens e SHA-256. Num contexto de 8192, slot único inicialmente vazio, medir o split de cada pedido a partir de `timings.cache_n` e `timings.prompt_n` ou das contagens de prompt/cached equivalentes verificadas, 0+121 e 122+313. O prefixo comum entre os dois arrays de prompt conta 121 IDs. O 122.º token depende da continuação do primeiro turno presente na KV. [Cliente e guardas C133](../two_turn_pair.py)
2. **Histórico natural.** Enviar os dois pedidos a `/v1/chat/completions` como a unidade C133. O segundo inclui a mensagem final efetiva do primeiro. Capturar conteúdo final, tempo de chegada e conclusão válida do SSE, aplicar o validador congelado. Um histórico diferente entra na medição de produto e perde a comparação causal de T2 com C133 quando os vetores diferem. O par de referência com histórico fixado é outro ensaio. A paridade isolada da Jinja ainda deixa por verificar a Jinja embebida, a tokenização que o servidor realmente usa e o estado da cache. [Critérios dos dois modos](../two_turn.md)
3. **Replay de IDs.** No stock `POST /completion` aceita diretamente arrays inteiros. Permite verificar a execução do target condicionada a IDs exatos, e `return_tokens=true` pode recolher os IDs de saída do endpoint nativo. O comparador tem de observar o split inicial no próprio pedido. `tokens_cached` no fim refere-se ao tamanho do slot após a geração. A medição de produto exige também a separação Harmony de raciocínio e conteúdo final, a validação funcional e os relógios SSE do endpoint chat. [Fonte do stock, entrada numérica](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/tools/server/server-common.cpp#L1105-L1118) · [Serializer da resposta](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/tools/server/server-task.cpp#L332-L355)

### Reprodução local

Os parâmetros `C269_SRC`, `STOCK_SRC` e `C133_RESULTS` referem as checkouts históricas C269, e95426f e o diretório results que contém o raw C133. Os diretórios de saída têm de ser novos. As mensagens trafegam unicamente por pipes privados. Nenhum prompt, ID individual ou resposta é publicado.

```sh
python3 -B research/qualification-retake/aster_template/verify.py \
  --c269-source "$C269_SRC" --c269-bin "$C269_SRC/build-c269-cuda/bin" \
  --stock-source "$STOCK_SRC" --stock-bin "$STOCK_SRC/../build/bin" \
  --historical-results "$C133_RESULTS" \
  --private-workspace "$NEW_PRIVATE" --new-output-dir "$NEW_REPORT"
```
