# Prefault e exatidão da fixture CPU

**MEDIDO — PASS_TINY_CPU_INFERENCE_AND_MMAP.** O carregador experimental com `TESY_STOCK_LAZY_MMAP=1` mapeou o GGUF sintético de 50 816 bytes sem `MAP_POPULATE` nem `POSIX_MADV_WILLNEED` sobre o mapeamento. O stock independente e o candidato com a opção desligada usaram ambos. Os 64 logits finitos dos dois prompts foram idênticos nos três clientes. Esta prova qualifica a mudança de mapeamento nesta fixture e admite uma decisão separada sobre o arranque do 120B sob o envelope E20. [Recibo R02](attribution-r2/receipt.json) · [Estudo do arranque até READY](startup.md)

| Processo | Mapeamento do inode do GGUF | Conselho sobre os 50 816 B | Produtos matriciais CPU por prompt | IDs greedy | Saída |
| --- | --- | --- | --- | --- | --- |
| Stock independente | `MAP_SHARED\|MAP_POPULATE` | `WILLNEED`, retorno 0 | 8 e 8 | 0 e 0 | 0 |
| Candidato OFF, valor `0` | `MAP_SHARED\|MAP_POPULATE` | `WILLNEED`, retorno 0 | 8 e 8 | 0 e 0 | 0 |
| Candidato ON, valor `1` | `MAP_SHARED` | Nenhum | 8 e 8 | 0 e 0 | 0 |
| Candidato, valor `invalid` | Rejeição no carregador | — | — | — | 25 |

Cada processo válido mapeou o ficheiro inteiro para leitura no offset zero. O conselho observado refere-se ao endereço mapeado. As chamadas sobre descritores de ficheiro e o número de leituras físicas têm semântica distinta. Para as entradas de IDs `[3,7,9]` e `[11,5]`, cada cliente produziu duas linhas distintas de 32 floats. O SHA-256 dos 256 bytes foi `aabc5c6e701c0df890d1fa21c9b590dcd4bf8a29f56390c1beb3f169848d1290`, igual também ao stock na primeira tentativa residente. O valor inválido produziu o erro explícito `TESY_STOCK_LAZY_MMAP must be 0 or 1`, sem ficheiro de logits nem evento de execução. [Recibo da referência anterior](r1/receipt.json)

A observação seguiu, em cada prompt, os oito despachos concluídos pelo backend CPU e o retorno de `ggml_compute_forward_mul_mat` da biblioteca `libggml-cpu`. Cada pedido do callback correspondeu ao mesmo tensor devolvido pelo kernel e à entrega após sincronização. O diagnóstico anterior de localização do buffer continuou a classificar os oito destinos como «outros». A biblioteca CUDA consta entre os cinco ELFs mapeados de cada braço válido. Os despachos observados foram todos CPU. [Protocolo de atribuição](attribution-protocol.md) · [Cliente e verificação dos fornecedores](attribution.py)

## Proveniência, orçamento e tentativas

O ensaio R02 correu em 25 de novembro de 2026 às 04:25:37 UTC na árvore limpa `2886fa63bb1b3911e9639515cc1169928465ddef` do commit `9f4e1641e648c3ae2c8294946af7b29ddf3a5dbc`, com o stock `e95426f16982054c379ca7bdc8186996dd22f0fe`. O recibo de build autentica as bibliotecas stock e candidata e o controlo recompilado byte a byte. O GGUF sintético SHA-256 `31a310d53e5c4c2a22994fc2fa75f095446af380885948120306fd6e7213a08d` foi gerado localmente. [Build](../stock_prefault_build/README.md) · [Recibo R02, SHA-256 0dbfbaf8f97e87ae31109e05eecba777227c57b5effe6c1b9191db5126d5047d](attribution-r2/receipt.json)

O relógio externo marcou 0,84 s e 266 392 KiB de RSS máximo. O supervisor mediu 0,756 s e 204 694 bytes de saídas antes do recibo. O pico cobrado ao cgroup foi 154 624 000 B com limite de 805 306 368 B e swap máximo zero. Todos os deltas de `memory.events` foram zero. O supervisor era o único processo nas duas fronteiras. Cada cliente teve até 8 GiB de endereço virtual e 90 s, dentro da janela de 180 s e 16 MiB para a unidade.

- Sob 768 MiB de espaço virtual, o carregador dinâmico falhou ao mapear uma biblioteca. Ao separar o limite de RAM e o virtual, o stock residente produziu os 64 logits, mas a atribuição pelo tipo do buffer falhou. [Tentativa de carregamento](../stock_prefault_build/tiny.md) · [Recibo residente R1](r1/receipt.json)
- A atribuição R01 executou os dois prompts stock e terminou em `FAIL_PRESERVED` antes de OFF por tentar chamar `st_size` como função. O replay dos mesmos bytes reproduziu o erro. A reparação na função Python autenticada alterou só esse acesso. O recibo da tentativa mantém SHA-256 `c6e4cc074c449023f4f5adad56114dd55013773836ccef54ce113cd8791e89e1`. [Recibo R01](attribution-r1/receipt.json) · [Reparação pré-registada](attribution-repair.md)

## Reprodução

Na checkout da medição, usar o Python com as dependências do escritor GGUF, o build stock B, o diretório privado do build candidato e a primeira referência residente. Reservar uma unidade transitória e um caminho de saída novos.

```sh
p=research/qualification-retake/stock_prefault_resident
python3 -B "$p/test_attribution.py"
python3 -B "$p/test_attribution_repair.py"
systemd-run --user --scope --unit="$NEW_UNIT" -p MemoryMax=768M -p MemorySwapMax=0 \
  "$PYTHON" -B "$p/attribution.py" --scope-unit "$NEW_UNIT" \
  --r1-root "$RESIDENT_R1" --stock-build-root "$STOCK_BUILD" \
  --overlay-root "$OVERLAY" --new-output-dir "$NEW_OUTPUT"
```

O orçamento desta unidade terminou após a confirmação CPU. A chegada a READY, a pressão do anfitrião e a paridade numérica do GPT-OSS-120B sob E20 dependem das respetivas medições. O tempo acima inclui a preparação e os quatro clientes da fixture. M3 continua PARTIAL e M4 NOT_MET. [Protocolo de recursos](protocol.md) · [Condições do teste E20](startup.md)
