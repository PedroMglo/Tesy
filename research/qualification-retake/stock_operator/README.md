# Projeção de experts MXFP4 com slots stock

**PASS_CPU_NATIVE_OPERATOR** na primeira fixture. O ClassLRU do pin e95426f escolheu os slots em seis planos de duas camadas. Em todos os planos, os pesos codificados lidos dos slots corresponderam ao expert e à camada certos. O GET_ROWS I32 do GGML produziu os IDs físicos esperados, e as três vias do MUL_MAT_ID produziram 9216 float32 finitos por braço, bitwise iguais por posição. A troca deliberada de dois IDs alterou a projeção. [Protocolo](protocol.md) · [Build R1](build-r1/receipt.json) · [Recibo CPU R1](cpu-r1/receipt.json)

O banco partilhado de oito slots teve 28 seleções distintas somadas pelos seis planos, 20 faltas, oito hits, 12 expulsões e oito recargas de chaves anteriormente expulsas. Cada expert da fixture ocupa 8704 B. O braço de reuso copiou 174 080 B. O controlo que voltou a copiar todos os experts selecionados nos mesmos slots copiou 243 712 B. A referência já tinha as duas camadas residentes e aplicou diretamente os IDs canónicos. O teste CPU durou 0,097 s e o maior RSS de filho foi 252 196 KiB, incluindo ferramentas de verificação. O nome local de uma variável usada para ler o nome do backend foi expandido no runner depois do R1 para cumprir o lint; o código do operador e o seu protocolo mantiveram as mesmas identidades. [Planner e API de cópia](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-moe-cache.cpp#L182-L285)

A fixture usa o planner selado da distribuição, o formato MXFP4 stock, as cópias explícitas para o buffer do backend e os operadores GET_ROWS e MUL_MAT_ID desse pin. A validação lê os dados do dispositivo depois da sincronização. Cobre a escolha, publicação e consulta de slots nessas condições. A distribuição real dos experts, o callback privado que lê as rotas, o agrupamento assíncrono das cópias, o scheduler, outros tamanhos de matriz, as reduções do FFN e o KV requerem provas adicionais. Compilação, vetores de diagnóstico e logs ficam no diretório privado. O recibo sela o executável, DSOs e bytes das saídas.

```sh
python3 fixture.py build --stock "$STOCK" --stock-receipt "$STOCK_BUILD_RECEIPT" --new-output "$NEW_BUILD"
python3 fixture.py CPU --stock "$STOCK" --stock-receipt "$STOCK_BUILD_RECEIPT" --build "$NEW_BUILD" --new-output "$NEW_CPU"
```

A execução CUDA usa a mesma interface em modo CUDA, numa janela exclusiva. Uma diferença fecha a igualdade bitwise na projeção observada. Se a igualdade também passar na GPU, o menor passo seguinte consiste em observar a entrega da rota pelo scheduler real e a primeira fronteira em que duas configurações divergem. O resultado C110 entre configurações completas mantém a sua decisão própria. [Comparação C110](../stock_numeric/README.md)
