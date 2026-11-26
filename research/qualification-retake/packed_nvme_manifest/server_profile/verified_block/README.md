# Pack de produto e grafo de verificação no mesmo backend

**GO para o ensaio numérico com o pack na reserva real do servidor.** O ELF experimental C291 incorpora a entrega pelo pack integral em NVMe e o grafo que já passou as rejeições no backend C269. Em C291, o compilador viu os mesmos 342 headers nos dois builds e foram reutilizados os mesmos 165 objetos além do grafo. A verificação das relocações passou no cliente e no servidor. O pacote de controlo obteve 18,313 s até ao primeiro conteúdo final e 5,361 tok/s no melhor turno nominal emparelhado. O desempenho da combinação continua NOT_RUN. [Resultado e hashes completos](result.json) · [Conversas anteriores](../conversation/ordens.md)

| Biblioteca | SHA-256 inicial | Exportações | Providers do cliente C270 | Providers do servidor C281 |
| --- | --- | ---: | ---: | ---: |
| RELINK, objetos do pack histórico | `1e21fef6` | 4 692 | 18 | 24 |
| RECOMPILE, grafo de controlo com GCC atual | `4d960c07` | 4 692 | 18 | 24 |
| BLOCK, reparações por posição com os mesmos flags de compilação | `7994ef4a` | 4 692 | 18 | 24 |

A primeira tentativa fechou ao exigir o hash integral histórico `04af70ea`. O ELF cresceu 48 bytes. A comparação binária encontrou os mesmos dez cabeçalhos de programa e 29 das 31 secções com conteúdo idêntico. Mudaram o identificador GNU do build e o comentário do GCC. No ensaio independente seguinte, a ligação dos objetos originais reproduziu byte a byte o ELF contemporâneo. As duas compilações e as três ligações demoraram 7,488 s no scope de 4 GiB com zero swap. Zero cargas do modelo e zero servidores. [Primeiro protocolo](protocol.md) · [Critério do controlo contemporâneo](protocol-current.md) · [Arquivo 174](../../../private_archive/part-174.json) · [Arquivo 175](../../../private_archive/part-175.json)

O servidor C281 chama `server_n_outputs_max`. Com uma sequência, batch 256 e geração normal, reserva uma saída sem proposta. No caso `NGRAM_SIMPLE`, `common_speculative_n_max` devolve o comprimento máximo da proposta, dois para N=2/M=2, e o servidor reserva três saídas. O log do braço P no ROP confirma a reserva 1. A fixture anterior deixou `n_outputs_max=0`; o construtor de contexto deste target resolve esse valor para 256. Na rejeição, o servidor usa a aceitação do sampler do target. O caminho de checkpoint depende da capacidade de remover o sufixo, com restauro para FULL ou para RS quando a profundidade excede a suportada. A qualificação anterior cobre a truncagem com o contexto vivo. O passo seguinte compara os cortes com as reservas de produto e os headers privados C291. [Protocolo numérico](server_reserve/protocol.md)

O verificador sem modelo reabriu os originais e as cópias seladas e produziu o mesmo compacto. Na pasta deste ficheiro, executar:

```sh
python3 -IB review.py "$BUILD_174" "$BUILD_175" | cmp - result.json
```
