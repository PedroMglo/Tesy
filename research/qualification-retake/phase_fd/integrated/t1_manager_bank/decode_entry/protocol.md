# Entrada do primeiro decode nas duas conversas C281 ON

**Pergunta.** Com as mesmas rotas do pedido T2 e diferenças já observadas na ordem de publicação, qual é a parte da tabela primária R0 que serve de referência comum na entrada do primeiro decode?

| Perfil ON | SHA-256 do recibo | SHA-256 do PFJ1 | Manifesto privado |
|---|---|---|---|
| T2, R02 | 78c3a5bb34353d2b880b14bfa80634cd06dfe465beec529446206a8728af3f43 | 1a96cca8af0fd2dd0a4e4fd1ba2afc031320e6ff0be9b335cead5f5e0035f018 | parte 37, 4c7715c643684b4b7b058fb20d0daea19c95d766a0a60aad43ce2cb29d9c2239 |
| Sufixo T1 + T2, R01 | fc368b04cc5ea6258c05594ab52306c336446f40ab06ea2ec5fe287eabfeef5d | 40d2ea8049ccee9213ffc3f317482d67ebbed85a887a933043a3f4e7bd132033 | parte 40, 4907245d68f604c31918d48d50259a60476ef76c1bfc0f848d98db659606b513 |

Usar só o prefixo até ao ENTER sob mutex da primeira chamada de largura 1 após 5+148 em T2. Conferir posições, tiles 32+32+32+32+20, ranks e identidades de procura nos dois prefixos. Reproduzir o auditor de conservação de cada PFJ selado, incluindo máscara da chamada de 5. O sufixo posterior serve apenas à conservação e à identificação das trajetórias já qualificadas. Preservar o FAIL do comparador histórico. Sem modelo, GPU, custos temporais transferidos entre relógios ou campanhas físicas.

Reproduzir, na ordem serializada do manager, o primeiro snapshot de 36×40 slots, reservas, fila FIFO com duplicados, despachos/claims, SKIP, cancelamentos e publicações até ao corte. No RETURN anterior conferir a fila e os claims declarados e incluir possíveis mutações até ao ENTER. Para cada camada publicar por braço contagens READY/LOADING/EMPTY, claims e fila, e comparar separadamente membros READY, atribuição expert→slot, geração por slot, estado, claims, trabalho por worker e FIFO ordenada. Selar com SHA-256 canónico cada projeção e publicar apenas contagens de diferenças e hashes. Documentar se parking é estado persistente ou escolha local da wave, que identificadores o PFJ realmente observa e que outros metadados do manager faltam.

**Decisão.** A coincidência identifica uma referência offline apenas para esses campos, nestes dois prefixos. Qualquer divergência de campo impede usar uma tabela única para o mesmo campo. Para um campo omitido declarar DESCONHECIDO e indicar a observação mínima. Nunca deduzir igualdade dos bytes, logits ou KV, política futura, neutralidade temporal ou um ganho de produto da igualdade dos descritores. O próximo gate exige controlo R0 contemporâneo na fixture de transição, com oráculos de consumidores independentes.
