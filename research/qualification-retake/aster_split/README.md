# O servidor stock reutilizou os 122 tokens

**MEDIDO, PASS para a fronteira da cache com SWA completa.** O GPT-OSS-120B original correu no portátil a partir do NVMe interno. O llama.cpp independente aceitou a sequência oficial de 435 IDs do segundo turno Aster e avaliou 313 depois de reutilizar 122. Um primeiro pedido de diagnóstico estabeleceu o prefixo conhecido. A qualidade da resposta completa a Aster continua por medir no comparador. [Protocolo congelado](protocol.md) · [Recibo físico](physical-r1/receipt.json) · [Prova sobre a variante compacta](../aster_cache_geometry/README.md)

| Pedido à mesma slot | IDs do prompt | Reutilizados | Novos | Tokens gerados | Prefill no servidor | Resposta completa no cliente |
|---|---:|---:|---:|---:|---:|---:|
| Preparação com prefixo fixo | 123 | 0 | 123 | 1 | 86,658 s | 86,692 s |
| Segundo prompt C133 | 435 | 122 | 313 | 1 | 211,257 s | 211,264 s |

O primeiro token é amostrado a partir dos logits do prefill. As duas respostas individuais deixam o custo de decode sustentado desconhecido. Os 341 e 452 tokens naturais da conversa histórica motivam medir o custo de vários passos seguidos antes de repetir a geração completa.

O stock ficou pronto em 31,488 s. Confirmámos as oito bibliotecas, modelo mapeado, cache CUDA de experts com 161 slots em 36 camadas, as duas reservas KV de 8192 células e o template com a data histórica. O processo esteve vivo 330,283 s e terminou com código zero. A campanha, incluindo 61 observações de C118, durou 390,871 s. O pico foi 4 362 MiB de VRAM e 10 203 529 216 B no cgroup E10, com high de 9,5 GiB, cap de 10 GiB e zero swap/OOM. A CPU chegou a 79,375 °C, a GPU a 50,38 °C e o NVMe a 57,85 °C. A energia isolada permanece desconhecida.

No intervalo inteiro do cgroup, incluindo a carga, io.stat contabilizou 758 965 817 344 B de leitura no dispositivo interno e 201 064 448 B no externo. O GGUF reside no interno e o executável/bibliotecas do stock no diretório do projeto. Atribuir esses contadores a um expert ou a um dos dois pedidos exigiria outro testemunho. Observaram-se 1 486 055 eventos high e sete eventos sock_throttled no cgroup. A política FILE_PAGING cobra o reclaim; houve 528 amostras de execução e o maior intervalo foi 0,825 s. Confirmámos a libertação da GPU e a remoção do scope.

A checkout de medição estava limpa no commit e5cf5de8dce69c07ebd7d0acc97b37507dbd1d0b. O recibo do supervisor tem SHA-256 ed55f7c2c5ec983d2c96b5c7ef1f4bd0740aed861bbe9d8661680486a65740b3 e confere os onze ficheiros privados. O armazenamento persistente preserva os pedidos e as respostas completos. O recibo público contém hashes, contagens e tempos. [Precheck sem modelo](precheck-r1/receipt.json) · [Índice do arquivo](../private_archive/part-05.json)

Para reproduzir, usar a forma de systemd-run do perfil E10 com uma identidade nova, trocar a entrada Python por research/qualification-retake/aster_split/probe.py e acrescentar o argumento --historical-results com a raiz local dos resultados C133. Usar o SHA da checkout limpa em --expect-head. O modo --before-inventory-only faz a verificação inicial antes de iniciar o servidor. Para medir os dois pedidos usar novas raízes privadas e omitir essa opção. [Comando do supervisor e argumentos de colocação](../aster_full_ready/README.md)
