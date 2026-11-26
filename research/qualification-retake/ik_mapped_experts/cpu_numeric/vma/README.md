# Inspeção das vistas dos experts no Btrfs do portátil

**PASS na fixture, incluindo o driver corrigido no GGUF sintético.** O D0
histórico R01 terminou com rc 34 na primeira matriz, antes de criar o contexto.
O observador exigia igualdade entre o dispositivo em `stat` e o dispositivo
em `/proc/self/maps`. Uma página mapeada do FD do original no NVMe, sem ler os
seus bytes, apresentou inode 40127919 em ambos, com dispositivos **0:56 em
stat e 0:38 na VMA** (major/minor em decimal). Essa condição antiga rejeita
uma vista legítima do original. R01 registou uma MAP integral de leitura e 72
MADV_DONTNEED concluídos, mas o erro agrupava as condições e descartou a VMA
da matriz. As permissões, offset e identidade dessa matriz específica continuam
desconhecidos no R01. Nada naquela mensagem permite atribuir uma discrepância
ao cálculo do router. [Protocolo](protocol.md) · [Observador anterior](../../tiny_loader/probe.cpp)

O driver autentica o FD de referência por tipo, stat, inode, tamanho e datas.
Depois do regresso do loader cria uma testemunha de uma página PROT_READ e
MAP_SHARED a offset zero, confirma o nome canónico e o inode, retém a chave da
VMA e desfaz o mmap. Só então lê os mapas dos tensores. Assim uma testemunha
temporariamente colocada num endereço livre nunca pode tapar uma lacuna na
verificação. Cada segmento precisa de ser r--s, corresponder ao nome e à chave
da testemunha e manter offset contínuo desde a base do mmap integral que o
interpositor viu abrir para o ficheiro autenticado. O supervisor conserva o
cruzamento dos offsets, tipos e tamanhos por nome contra o inventário C283.
O path de abertura pode ser um symlink para o path canónico. O tensor pode
atravessar várias VMAs. O custo do observador é uma página virtual temporária,
duas leituras de mapas e zero dereferências do seu conteúdo. A observação é
exterior à janela nativa de contagem das MAP do loader. [Precedente de autoridade por VMA](../../../nvme_r0_gate/qualified_profile/authority.py) · [Implementação](inspect.hpp)

| Prova | Resultado |
|---|---|
| Ficheiro sparse e nome com espaços em tmpfs | Offset correto 4 294 967 343, intervalo aceite depois de DONTNEED e através da divisão por MADV_RANDOM |
| Oito controlos | Rejeitados FD alheio, dispositivo, nome, inode alheio no segundo segmento, segmento gravável, segmento anónimo, offset deslocado e lacuna |
| Ficheiro regular de controlo na raiz Btrfs | Inode coincidente, stat 0:40, VMA 0:38, munmap confirmado |
| GGUF sintético R04, 16 posições + 1 teacher | 12 vistas, uma única MAP do modelo, 16/17 células KV, dois vetores de 32 F32 idênticos em D0 e D1, máximos únicos 6 e 23 |
| Paragens deliberadas | rc 42/43 antes do teacher e 44 depois do segundo vetor. Calibração, D0 e D1 rc 0. Pico de cgroup 59 736 064 B com cap 256 MiB, zero swap/OOM, scope final inactive/dead |

O source foi congelado em `66a7e837`, com protocolo prévio `ad667e1e`.
O teste sparse usa os mapas do próprio processo e um ficheiro sintético truncado,
com zero blocos alocados à entrada. Um ficheiro regular opcional de pelo menos
uma página permite reproduzir a diferença de dispositivos no filesystem local.
Usar destinos novos e compilar com o compilador do projeto.

```sh
c++ -std=c++17 -Wall -Wextra -Werror -O1 fixture.cpp -o "$NEW_BINARY"
"$NEW_BINARY" "$NEW_DIR" "$NON_MODEL_REGULAR_FILE"
```

A família de seis processos reutiliza os comandos, pesos sintéticos, referências
e controlos da família R03. A identidade do novo header e do seu protocolo
entra no recibo do build. [Build e comandos do supervisor](../driver/README.md)

| Recibo privado | SHA-256 |
|---|---|
| D0 real R01, FAIL preservado | `7e48b95fc8274c008fad02fd03ee9831892a162ba5c8498f1f0a725524152f29` |
| Testemunha de uma página no GGUF original | `9539582254472d89c166a39c025f4c1a796fca71378aafae4002b55594ff3e16` |
| stdout da fixture sparse R01 | `41bdbdcd9a8c38cafb4d3e687a93e7e68b8768f103dbfcdf97aef995c1bb2ecc` |
| Build R04 | `25179675325e8eca59567b930b76c756d81e1b0e69f7935fe678b464d5ac6e7a` |
| Executável R04 | `9176eeabd2497fffed6f7dcf592ceb2d88541496b7aa1f621d6eb29f3e1b00c2` |
| Família numérica sintética R04 | `793c115463a6609b51820d84f02a6dcde83b998c292e00d64ce7805b0e349866` |

A decisão admite a nova inspeção do canário. A qualificação de routing,
logits e serviço do original depende dos braços do protocolo C110.
