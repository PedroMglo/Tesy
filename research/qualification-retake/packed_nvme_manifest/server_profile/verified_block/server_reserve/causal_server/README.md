# Propostas causais nos dois turnos naturais

**GO para uma sessão diagnóstica no servidor.** O dispatcher C281 reproduziu ambos os turnos com a política bigrama, até duas propostas e o histórico confirmado pelo target. O primeiro turno teve três aceitações parciais, uma situação ausente do segundo turno. Os dois replays e a revisão a partir do arquivo deram o mesmo resultado.

| Turno | IDs de entrada | IDs gerados incluindo EOG | Chamadas de 1 posição | Blocos de 3 | Aceitou 0 / 1 / 2 | Custo médio máximo do bloco no empate |
|---|---:|---:|---:|---:|---|---:|
| T1 código | 2 043 | 78 | 57 | 9 | 2 / 3 / 4 | 2,222 × um passo serial |
| T2 repetição | 2 197 | 47 | 23 | 11 | 5 / 0 / 6 | 2,091 × um passo serial |

O primeiro ID vem do prefill. Os limites de empate comparam as 77 ou 46 posições restantes sob a hipótese de custo serial uniforme. As 66 e 34 chamadas do replay dão o mesmo número de tokens confirmados que o serial. A fixture separada de cap 3 truncou uma proposta real para um único ID. Nos turnos naturais não houve truncagem nem bónus desconhecido. Frequências e bytes da fixture de 189 posições não determinam quantos segundos se poupam em nenhum dos turnos. O resultado é TRACE_DERIVED, com zero pedidos ao modelo, GPU ou HTTP.

A primeira execução parou na ligação da dependência direta de `llama_max_devices`. A segunda expôs que a CLI acrescenta `ngram-simple` ao valor inicial `none`. Ficaram os dois FAIL, os logs, os binários produzidos e o resultado favorável, em 22 ficheiros privados, 1 772 293 bytes. A terceira execução durou 2,46 s, com cap 1 GiB e swap zero. A revisão offline lê os dois vetores de referência e todas as linhas de proposta. O seu resultado tem SHA-256 `04f02d51e8403d40a86782a33145347dd545c5bbc56ff2c332d05e41e97c0750`. [Protocolo](protocol.md) · [Comparação compacta](result.json) · [Manifesto privado](../../../../../private_archive/part-177.json)

O teste seguinte mede os dois pedidos do cliente C281 no servidor local, confirma os IDs de cada turno e observa o custo da especulação paga pelo target. O melhor T2 emparelhado até aqui mediu 18,313 s e 5,361 tok/s. M3 PARTIAL e M4 NOT_MET mantêm os seus contratos. [Limite de custo no T2](../../../../../history_lookup/packed_step_budget/frontier.md)
