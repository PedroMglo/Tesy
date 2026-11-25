# Localização da diferença KV após três posições

Diagnóstico retrospectivo de uma diferença já conhecida na família R01
(`97ae7b5b9c9deed4e730fb1ddb50cdbd6d671aeea5169f73db2c96f49b40a7d9`).
Estas regras antecedem a inspeção dos offsets e conteúdos dos quatro snapshots.

O pin C269 é `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`.
`llama-context.cpp:2972` escreve magic e sequência, depois delega à
memória. O escritor host copia com `ggml_backend_tensor_get`.
`llama-kv-cache-iswa.cpp:259` emite primeiro o banco base, depois o SWA.
`llama-kv-cache.cpp:1973,2086,2119` grava os metadados das células e, por
banco, todos os K antes de todos os V, por camada e pela ordem das células.
Com atenção flash e F16 cada linha tem 512 elementos e ocupa 1024 bytes.
Atribuir as 18 camadas ímpares ao primeiro banco e as 18 pares ao segundo
depois de verificar as mensagens de colocação de ambos os filhos. A janela
SWA de 128 exclui as células anteriores mesmo com alocação integral de 8192.

Autenticar o código, a família, os filhos, os seus stderr e os quatro
snapshots. Exigir uma stream por banco, sequência zero, posições contíguas
esperadas, tipos e tamanhos declarados, V sem transposição e EOF exato.
Comparar cada valor F16 por bits, incluindo zeros de sinal distinto e
não finitos. Separar metadados, posições anteriores a 189 e novas posições
189–191. Identificar a primeira diferença na ordem do ficheiro e a camada
de menor índice afetada. Verificar se as posições de entrada sobreviventes
mudaram entre os dois cortes dentro de cada braço. Se o formato não puder
ser demonstrado, fechar como inconclusivo. Publicar apenas índices,
contagens e hashes, sem valores nem vetores privados. Esta localização não
estabelece a origem da primeira diferença do grafo ou dos logits.

Orçamento para o verificador sem modelo: 60 s, 256 MiB, sem GPU.
