# Renomeação dos slots na continuação nominal C163

**TRACE_DERIVED. Há uma trajetória admissível com zero cópias de reconstituição de payload** nas 47 chamadas de decode fornecidas pelos dois braços nominais C163, com 44 slots por camada e as agendas da fixture EARLY e LATE. À saída do prefill, 122 slots têm outra identidade física. A bijeção que associa o mesmo expert lógico nos dois pools conserva a ordem do parking e das vítimas em todas as 36 camadas. As 33 posições vazias CUDA coincidem fisicamente, e a CPU tem os seus slots preenchidos. Conservam-se a ordem relativa da recência incluindo empates, hotness, keep e claims. As gerações, contadores de uso e valores numéricos das idades diferem em 23 camadas. [Protocolo](iso_protocol.md)

Nas chamadas 11–57, posições 2197–2243, a referência reproduziu todas as 6 768 procuras, 1 210 evicções e 1 243 reservas do journal e as estruturas das 36 camadas no snapshot final. O candidato conservou os seus próprios payloads e identificadores. As 9 221 ações coincidem com a referência por expert e, sob a bijeção fixa, por slot físico e geração relativa. A comparação subtrai uma constante por slot entre os contadores de geração, fixada antes da chamada 11. O contador de tickets conserva a diferença de −50. No fim ainda há diferenças de idade numérica dos residentes nas camadas 11 e 28, com a mesma ordenação em ambas.

Esta equivalência satisfaz a continuação lógica observada se o runtime puder conservar o seu mapeamento natural em fronteira quiescente. O custo de restaurar literalmente todos os endereços permanece aplicável a uma interface que exija esse estado físico. O ensaio usa as rotas do target como entrada fixa. Uma experiência do backend teria ainda de validar a remarcação nos kernels, os valores das lanes mascaradas, KV, logits e o primeiro decode antes de atribuir tempo ao pedido. As posições após 2243, os holdouts, C135 slots40 e a conversa de produto ficam fora desta evidência. [Verificador](isomorphism.py) · [Recibo](iso-evidence/receipt.json)

Da raiz do repositório, com a pasta raw de C163 em leitura e um destino novo:

```sh
python3 research/prepin44/isomorphism.py \
  --repo . --replay-dir research/prefill44-replay --policy-dir research/prepin44 \
  --raw-dir "$TESY_C163_RAW" --new-output-dir "$NEW_ISO_OUTPUT"
```
