# Pode uma escolha melhor aproveitar os 353 lugares?

**TRACE_DERIVED.** Uma lista escolhida conhecendo T2 cabe nos 353 lugares e, aos preços do mesmo processo serial, abre margem nos dois alvos. A política utilizável durante T1, baseada na contagem de ofertas, falha os dois. Todos os tempos abaixo supõem o prefill reduzido ao serviço mínimo do NVMe e o serviço evitado de decode inteiramente exposto. O pedido físico com esse binário em serial fez 18,271 s e 5,332 tok/s. [Protocolo](offers-protocol.md) · [Resultados e testemunhos](offers-result.json)

| Seleção fixa ao fim de T1 | Reservas cobertas no prefill / decode | Comuns às 35 | Aquisição CPU / CUDA em GB | Primeiro final e decode projetados | Com as 35 recuperações |
|---|---:|---:|---:|---:|---:|
| Últimas ofertas | 155 / 172 | 3 | 42,804 / 16,762 | 10,601 s / 5,845 tok/s | 10,507 s / 5,845 tok/s |
| Contagem de ofertas | 214 / 186 | 5 | 33,616 / 12,505 | 10,454 s / 5,828 tok/s | 10,366 s / 5,828 tok/s |
| Volume futuro, testemunho | 437 / 371 | 9 | 3,344 / 1,322 | 9,516 s / 6,147 tok/s | 9,439 s / 6,147 tok/s |

Houve 4 548 ofertas de vítimas READY em T1, de 2 829 identidades distintas. A lista retrospetiva é materializável na primeira oferta de cada chave se a lista se souber antecipadamente. Isoladamente, 353 chaves podem cobrir até 523 reservas de prefill fora das 35 e até 445 reservas de todo o decode. Os dois máximos permitem escolhas distintas. A lista construída somando o volume das duas fases cobre 463 reservas de prefill na união com as 35. O verificador refez os caminhos com os preços seriais e confirmou as decisões online em todos os prefixos das 81 sequências pequenas da fixture. [Seleção e conferência dos recibos](offers.py)

**NO_GO para adoção da contagem de ofertas.** Com as 35, o seu melhor caminho fica a 365,685 ms do prazo do cliente. A recência continua melhor em débito de decode. **INCONCLUSIVE para transformar a lista futura numa receita.** O cenário com a lista retrospetiva exige pelo menos 74,2432% de exposição do serviço de decode. Mesmo no cenário de exposição total, o prefill sozinho só recebe 1,966 s na projeção sem as 35. A primeira verificação é confrontar esta hipótese com os intervalos do prefill medidos fora dos callbacks de experts. A seleção não tem ainda uma previsão causal com esse nível de acerto.

As duas execuções na árvore limpa de `ea16e6db1383f7f7a5ada9be1ddd19bb10b704c5` duraram 4,063 e 4,057 s, com picos de 118,5 e 119,7 MiB, zero swap, GPU ou pedidos novos. O resultado tem SHA-256 `67981e087f60d99bb6991fca60b61721f70373749262b39e49902c3c2d9d3b90`. [Recibo de quatro ficheiros, 16 158 B](../../../../../../../../../../../../private_archive/part-197.json)

Para reproduzir, usar o [comando da parte 196](joint.md) com `offers.py`, o commit acima e outro destino vazio.
