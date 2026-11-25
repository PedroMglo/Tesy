# Journal do serviço por geração no worker C291

**GO para a fixture de observação do pack.** Nos cinco processos, o manager C291 original serviu os bytes esperados em GGML CPU e a extensão do PFJ reconciliou os trabalhos das threads com chamada, tile, camada, expert, slot e geração. O snapshot inicial conservou os 1 440 slots e os 108 pesos. Na primeira tile foram pedidos os experts [0,1,2,3] e na segunda [0,1,2,4]. Os braços OFF e ON de cada transporte emitiram a mesma seleção e a mesma contabilidade nativa. [Pré-registo](protocol.md) · [Recibo e hashes](evidence/receipt.json)

| Braço | Tentativas | pread efetivas no kernel | B devolvidos ao leitor | SET | B entregues e verificados | Publicações | Erros de geração |
|---|---:|---:|---:|---:|---:|---:|---:|
| GGUF OFF e ON (cada) | 15 | 15 | 66 146 304 | 15 | 66 096 000 | 5 | 0 |
| Pack OFF e ON (cada) | 6 | 5 | 66 109 440 | 15 | 66 096 000 | 5 | 0 |
| Pack ON curto | 1 | 1 | 13 219 199 | 0 | 0 | 0 | 1 |

O teste injeta EINTR à primeira tentativa de e0 antes da chamada de sistema, e o leitor nativo repete-a. O total de bytes **pedidos incluindo o retry** é 79 331 328 no pack positivo. No negativo o kernel completa a operação e a fixture encurta o retorno observado pelo leitor a um byte abaixo do payload. O worker removeu o claim de e5, conservou a geração LOADING e assinalou a falha. O índice do pack e os ficheiros de pesos são sintéticos. Quatro workers terminaram em cada braço, sem registos perdidos nos três journals.

**Relógios.** Em GGUF ON a soma dos intervalos de serviço dos workers foi 37,789 ms, com união de 13,525 ms em parede. No pack ON foram 32,997 e 11,664 ms, respetivamente. Cada tentativa de pread e cada SET contribuem com o seu próprio intervalo início/fim. A união exclui os períodos sem nenhum dos dois tipos de serviço. O erro de e5 só regista a leitura. Os inputs esparsos, o retry injetado e um processo por configuração permitem verificar a reconstrução temporal. A latência do servidor e o custo do tracing em T2 ficam NOT_RUN. [Auditoria independente](audit.py)

**Fronteira nativa.** O patch aplica-se ao C291 `c89c88b342054223e3f27a17fbfd0954803147ac`. O intérprete de PFJ1 conserva o layout de 96 B. Foram acrescentados PACK_FILE e PACK_READ. A leitura do pack regista o FD, a tentativa, offset, comprimento alinhado, bytes devolvidos e errno. Cada SET observa o papel, destino e a origem em staging. O worker publica somente depois de repetir a validação do claim sob o mutex. O leitor GGUF segue o ramo original do C291. A fixture extrai de llama-context.cpp os pontos de medição que rodeiam o grafo de cada ubatch e a chamada externa. O controlador conduz estas fronteiras e um grafo de remap CPU real; a chamada exterior tem um substituto controlado. Não foi construída uma nova DSO para o servidor nesta unidade.

A aresta entre waves de uma camada é a vista do acumulador anterior que entra no próximo nó de IDs. Na primeira wave da tile e no ramo uniwave essa aresta não está presente. O retorno do SET CUDA no stream da thread de I/O comprova a entrega dos pesos. Para atribuir a última utilização deve-se seguir os consumidores de pesos, as dependências do grafo e os joins que efetivamente abrangeram aquele slot. A primeira observação posterior que garanta conclusão dá um limite superior. O journal desta fixture não mede esse instante e não acrescenta fences ou callback de avaliação. A promoção de um preload, a máscara efetiva por posição, os pins e o custo integrado da monitorização requerem qualificação separada no P. [Observação pretendida](../packed_prefill/observation.md)

**Recursos e reprodução.** A execução R02 usou 4,971 s incluindo compilação, pico do cgroup de 391 557 120 B, cap de 1 GiB e swap zero. Os dois ficheiros de teste em Btrfs ocupam 184 320 B em blocos para 192 798 720 B de tamanho lógico. A primeira tentativa R01 parou antes dos dados porque o teste de loader procurava a palavra cuda no caminho completo das próprias bibliotecas CPU/base. R02 verifica nove SONAMEs e os caminhos/digests reais das bibliotecas CPU/base. Nenhum braço físico foi executado em R01. [Patch C291](observer.patch) · [Verificador da fixture](run.py)

A partir da revisão R02 `5e84957dc4a7c24bed418db440f0cac5033c3b0a`, nesta pasta e com quatro variáveis de caminho apontadas à checkout C291, às duas DSOs pinadas e a dois destinos exclusivos (o segundo em Btrfs):

```sh
python3 -IB test_native.py
python3 -IB test_audit.py
systemd-run --user --scope --quiet --unit="$UNIT" -p MemoryMax=1G -p MemoryHigh=1G -p MemorySwapMax=0 \
  /usr/bin/python3 -IB run.py --backend "$C291" --libs "$C269_LIBS" \
  --commit 5e84957dc4a7c24bed418db440f0cac5033c3b0a --scope-unit "$UNIT.scope" \
  --new-output-dir "$NEW_OUT" --new-data-dir "$NEW_DATA"
python3 -IB audit.py family "$NEW_OUT"
```

O recibo R02 tem SHA-256 `625b0e50c920938e478ff5b2f2a8bd0c85bbe2fb1f78fa4278f0e040f2ea3759` e a falha R01 `b894a834ef5565ae9be953b6116a988ef560234c1263ae54d99c791d4e55b1b5`. A próxima etapa é autenticar a DSO com o mesmo overlay, confrontar OFF/ON com trabalho idêntico e só depois recolher as duas chamadas de prefill do cliente natural.

Os cinco processos, a primeira tentativa e a reabertura independente ficaram na [parte 92 do arquivo privado](../../../../private_archive/part-92.json).
