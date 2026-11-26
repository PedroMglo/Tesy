# Conversa natural com o leitor seletivo do Tesy

**MEDIDO no portátil, 26 de novembro.** O servidor completou e validou os dois turnos C281 com o GPT-OSS-120B MXFP4 original. O turno incremental reutilizou 2 044 tokens do histórico gerado pelo próprio servidor. Processou os 153 esperados e produziu 51. O primeiro conteúdo final chegou aos **46,246 s** e o decode fez **1,696 tok/s**. Faltam 36,246 s e 4,304 tok/s para os dois alvos. M3 PARTIAL, M4 NOT_MET. O GO previsto admite a ablação emparelhada do leitor. [Protocolo prévio](session-protocol.md) · [Recibo público](result.json)

| Turno | Prefixo + processados | Saída | Prefill (s) | Decode (s) | Decode (tok/s) | Primeiro raciocínio (s) | Primeiro final (s) | Resposta válida (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T1 | 0 + 2 043 | 78 | 50,536 | 45,777 | 1,704 | 52,266 | 95,336 | 96,327 |
| T2 | 2 044 + 153 | 51 | 17,178 | 30,072 | 1,696 | 18,977 | 46,246 | 47,264 |

Os dois pedidos locais acabaram com stop natural. Os relógios de prefill/decode vêm do servidor, os outros três do cliente. O cliente confirmou os dois hashes de IDs de entrada. A API não expôs os IDs de saída neste caminho. O ensaio qualifica estes dois textos e a reutilização de histórico. A paridade bit a bit com o ik GPU foi medida nos dois cortes fornecidos C110. A melhor sessão emparelhada do pack anterior fez 18,313 s e 5,361 tok/s. Este cruzamento entre backends tem trajetórias próprias e cache inicial diferente. [Quatro braços do pack](../../../packed_nvme_manifest/server_profile/conversation/ordens.md) · [Numerical do leitor](../../hybrid/cold_gate/backend_input/bounded/native_hook/c110/README.md)

O driver era 620.73.04. O pico foi 6 206 MiB de VRAM e 16 105 648 128 B no cgroup, com zero swap. Antes da janela C118 havia 15 908 900 864 B do GGUF na cache de páginas. A prontidão demorou 3,032 s. No encerramento o leitor contou 7 025 seleções, 63 099 SET, 291 126 441 600 B de payload solicitado e 14 esperas adicionais por capacidade. Estes contadores abrangem os dois pedidos e o journal CUDA estava desligado. O monitor terminou com código zero, o processo saiu e o serviço ficou inativo. Energia integrada desconhecida. A campanha abriu o modelo uma vez e fez dois pedidos de geração, sem downloads.

Execução em `6ec35dbf`, árvore `1f30cb18957d21e8f76c54b1c623ea719cf69151`. O auditor reconstituiu os dois conteúdos a partir dos deltas SSE, as suas primeiras aparições no relógio do cliente, o histórico e os dois validadores. Os 35 ficheiros privados somam 1 464 169 B. Os originais e o arquivo produziram recibos públicos idênticos com `python3 -IB review.py --family "$FAMILY" --family-sha256 8fc33c06313d1a5888fb1bbb75c9c95cef361382fc6bfd127b0781b4962d602b --new-output-dir "$NEW"`. [Auditor](review.py) · [Manifesto 160](../../../private_archive/part-160.json)

## Binário do servidor

**REPRODUZIDO · GO_SERVER_ELF.** O mesmo executável HTTP do pin `7a5d90009b7ae55d3239cdd33244977c4eb10ff6` resolveu a biblioteca original e o hook nativo do Tesy. Os outros quinze fornecedores coincidiram em caminho e SHA-256 em ambos os testes de resolução. Os dois ensaios de versão reportaram `7a5d900`. O GGUF que servirá a conversa é o original já verificado no NVMe. O binário tem SHA-256 `3447f8b883d4bb2bd301e05ee7d3c71088e318a387da6e5c3c2906588365907c`. [Construção](build.py) · [Protocolo](protocol.md)

A partir da configuração CUDA do portátil e de uma cópia limpa do pin, o Ninja compilou as 42 unidades do frontend, HTTP, common e mtmd. A build importou os dois DSOs SM89 verificados. Durou 110,058 s, escreveu 234 409 127 B, teve um pico de 2 432 364 544 B no scope e usou zero swap. O namespace de compilação não tinha rede, pesos ou dispositivos GPU. O commit da build é `c09204cd`. O arquivo conserva o ELF, mtmd, comandos, resolução, versão e recibo `3bad85a508f91896daee9c8ceb922f37e3acd495ab0213ea68fc30a80cfe43ec`. [Manifesto 159](../../../private_archive/part-159.json)

O servidor usa PREAD, a capacidade provada e o cliente C281. No fork é necessário desligar explicitamente flash attention e as três fusões para reproduzir a configuração numérica do C110. O contrato de cache cruza `usage.prompt_tokens_details.cached_tokens` com `timings.prompt_n` e os IDs oficiais. [Frontend verificado nos dois históricos](../README.md)
