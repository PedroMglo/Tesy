# O indexador do fork reconhece as 108 matrizes e os 108 bias do original

**PASS do indexador do loader.** Com o cabeçalho autêntico do GGUF, o construtor CPU de `ik_llama.cpp` reconheceu a arquitetura GPT-OSS e reproduziu os 687 nomes, formas, tipos, offsets e tamanhos do inventário C283. O índice de deferência contém 72 intervalos contíguos. Cobrem precisamente as 108 matrizes MXFP4 e os seus 108 bias F32, num total de 61 073 326 080 B. Restam 2 300 997 888 B de pesos e outros tensores fora do índice. Os dados da tabela são comprimentos lógicos no ficheiro. [Protocolo](protocol.md) · [Recibo](result.json)

| Tipo de tensor diferido | Tensores | Bytes |
|---|---:|---:|
| Matrizes de experts MXFP4 | 108 | 60 914 073 600 |
| Bias de experts F32 | 108 | 159 252 480 |
| Restantes tensores | 0 | 0 |

O revisor leu 13 022 240 B de cabeçalho do original NVMe. O processo que executou os braços OFF e DEFER recebeu uma vista esparsa selada com 13 025 280 B alocados. A extensão lógica permitiu ao fork validar o fim de cada tensor. Ambos os braços construíram explicitamente o mesmo índice. Só DEFER autorizou usar esses ranges no mmap. O controlo com a extensão lógica encurtada em um byte foi rejeitado pelo guardião de tamanho do fork. As duas execuções, em 1,51/1,52 s incluindo compilação, deram o mesmo SHA-256 `36209e35a8e04f672270108aeb70420f18b37c6536ced7eb906a66aa0f02234f`. Maior RSS dos processos de preparação de 304 604/304 668 KiB. Nenhum processo recebeu bytes originais dos pesos. A residência no arranque e a disponibilidade dos bias/experts no grafo real pertencem a outra medição. [Cliente da biblioteca R03](index.cpp) · [Construção da vista e conferência dos offsets](verify.py)

```sh
python3 -IB verify.py --source "$IK" --build "$BUILD_R03" \
  --model "$GGUF_INTERNO" --inventory "$INVENTARIO_C283" --new-output-dir "$NOVO"
cmp "$NOVO/receipt.json" result.json
```

Usar a checkout Tesy congelada em `14f74405` para reproduzir integralmente a identidade do recibo. O sinal valida o formato e o índice de deferência que evitariam o prefault inicial dessas matrizes nesta configuração. Aí termina o âmbito da comparação.
