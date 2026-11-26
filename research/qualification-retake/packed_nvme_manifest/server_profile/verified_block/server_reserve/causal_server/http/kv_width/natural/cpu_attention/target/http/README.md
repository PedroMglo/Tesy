# Controlo serial do servidor com o ELF corrigido

**GO para medir os dois turnos.** No primeiro bloco natural de T1, o 120B com a proposta desligada reproduziu bit a bit os cinco vetores de 201 088 logits finitos, os estados de KV à entrada e à saída (80 869 972 B no final), os 20+3 IDs e os dois pools do C291 independente. Tal como o controlo, fez 141 cargas e pediu 1 863 907 200 bytes lógicos de pesos no bloco. A execução serial usa a mesma biblioteca que o braço especulativo da parte 182. [Protocolo](protocol.md) · [Resultado compacto](off-result.json) · [Referência](../README.md)

| Ensaio | Observação | Estado |
|---|---|---|
| OFF inicial | Um arranque, zero distribuições capturadas. O supervisor encerrou o processo por encontrar o nome `ld.so.cache` entre os mapeamentos. Faltam as permissões e o inode desse mapa original. | FAIL preservado |
| Fixture do supervisor | A primeira tentativa com mmap partilhado falhou. Com um mapa privado real do índice glibc e a libc do processo, o inventário de bibliotecas coincidiu com o controlo e dez adulterações foram rejeitadas. | FAIL preservado e GO para a nova observação |
| OFF serial corrigido | Um arranque, zero pedidos HTTP. O alvo reproduziu a referência de 182. Nas 274 passagens do observador, o mapa transitório do índice foi visto zero vezes. | GO numérico |

O último processo durou 69,648 s incluindo captura e serialização. A campanha durou 131,385 s com C118 de 61 amostras, cap de 20 GiB e zero swap no cgroup. A energia estimada da RTX foi 1 021,6 J em 68,972 s de cobertura. As medições de latência do cliente pertencem à sessão HTTP. Os 52 ficheiros do arquivo privado ocupam 86 180 618 B. A revisão dos originais e a revisão da cópia privada reproduziram o SHA-256 `13550ffcae0cbbb1d8d2688cac4d14f72e59a2f6e1b9a637c2c0b3ea7d0c490b`. [Controlos do observador](loader_protocol.md) · [Revisor](review_off.py) · [Manifesto privado](../../../../../../../../../../../private_archive/part-183.json) · [Comparação de quatro braços](serve.py)
