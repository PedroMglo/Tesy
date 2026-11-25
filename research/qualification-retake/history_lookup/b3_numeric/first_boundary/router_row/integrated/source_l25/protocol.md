# O primeiro router CUDA recebe a mesma ativação nas duas geometrias?

Auditoria estática de controlos encerrados. A divergência no router da camada 25 já é conhecida. Antes de abrir os índices e as diferenças por posição, fixar o teste. Para 189 e 190, procurar separadamente AR, B3 original e B3 com o router fatiado: `l_out-24`, `attn_norm-25`, Q/K/V, saída de atenção, residual `ffn_inp-25`, `attn_post_norm-25` e produto router *antes* do bias. Só uma linha F32 autenticada, na posição, camada e ramo certos, conta como captura de um operando. Marcar separadamente top-4, FFN, pool, cache KV serializada e falta de um dos lados. Não comparar índices de slots como se fossem ativações. Sem novos pesos, forward ou trace físico.

Traçar na fonte a cadeia até ao produto antes de bias e as condições de colocação/dispatch para uma ou três posições. Distinguir o destino indicado no log da execução comprovada do kernel, as entradas idênticas do construtor e os seus bytes em runtime. Se ambos os lados do último input e do produto já existirem, reabrir e confrontar bits. Se faltar input correspondente, especificar a menor captura prospectiva que separe erro recebido de erro produzido no router e um controlo negativo. Fontes são o pin C269 `d0ebfbcc6c8f456bc1083027c1b08075a32824d8` e a única TU derivada `3ba064e64cc834f08dc6edf721be07c7013fc2f4b6641b3de13003488e4c2f71`. Hashes SHA-256 do original:

| Fonte | SHA-256 |
|---|---|
| src/models/openai-moe.cpp | 239407aaa98f8b65eb280e4423588ba7cefc520371811b9c47d7457fc1f469d4 |
| src/llama-graph.cpp | d1a2ce42e649305416665091ecee4523c1638721d42cca34b51a03bbcfce3288 |
| src/llama-model.cpp | 7af9ef3bb6dc9491f7280b3dbcc4f6605da7739b4288e7bee51881772f58f010 |
| src/llama-context.cpp | 7d8cfa9f33f38d761cf18b8e548ab7811866fbb8fdfaa95eeb2211d56851681b |
| ggml/src/ggml-backend.cpp | a96b54377e2b66732dcc5ed7ede82b6e0e873de53d515ac9fd6aa118b716bdd3 |
| ggml/src/ggml-cuda/ggml-cuda.cu | 0de01a8cb0502a7eea43b130504dcfeebb6fbf9dce31c57f884337419b7071d5 |

Admitir os inventários C127/C270, os observadores de first_boundary e as suas referências numéricas encerradas. Reutilizar esses recibos. Atribuir a diferença a um método de cálculo exige identificar o lançamento efetivo ou isolá-lo a entradas idênticas.
