# Memória que o banco de vítimas pode partilhar com os slots CPU

**SIMULADO.** Na entrada do T2 há 36 das 353 vítimas também no primário CPU.
Partilhar o backing dessas gerações pode libertar até 475 987 968 B. Outras
12 vítimas têm os pesos em VRAM e a cópia do banco em RAM. A construção
causal que usa estas páginas para prolongar a LRU de T1 chegou à entrada com
49 chaves adicionais, incluindo 14 já presentes no primário CPU. No mesmo
pedido poupou **14 das 1 058 leituras do prefill e 4 das 797 do decode**.
São 18 admissões, 16 experts distintos, 237 945 600 B úteis. O ganho de
capacidade pode integrar a combinação. O tempo do pedido continua por medir.

| Interseções com o banco fixo | CPU no carry | CUDA no carry | CPU READY em R0 | CUDA READY em R0 |
|---|---:|---:|---:|---:|
| Entrada no T2 | 36 | 12 | 36 | 12 |
| Mín.–máx. na call 5 | 35–41 | 9–12 | 36–50 | 12–15 |
| Mín.–máx. na call 148 | 29–80 | 10–29 | 50–96 | 15–32 |
| Entrada no decode | 80 | 29 | 96 | 32 |
| Mín.–máx. em 46 passos | 8–80 | 1–29 | 96–122 | 27–37 |

As camadas 0–24 têm 1 000 slots CPU e as 25–35 têm 440 CUDA. Contam-se
pares camada/expert distintos. A tabela de R0 conserva só READY nos eventos
do journal físico e cruza esses vínculos com o banco hipotético. O carry
identifica a sequência de reservas, sem medir a publicação nem o último
leitor. Os máximos potenciais de páginas CPU vão de 105 775 104 B (8) a
1 057 751 040 B (80). A capacidade libertada depende do último acesso à
geração antiga e da nova vista estar instalada. A série por camada, com os
52 retornos de tile ou passo e o corte inicial, consta do [recibo](receipt.json).

A RAM densa dos slots CPU tem 13 219 200 000 B úteis. Nas vistas de páginas
o padding acrescenta 2 688 000 B. Os pesos do primário CUDA ocupam
5 816 448 000 B de payload. O pico **MEDIDO** de R0 ON foi de 15 940 538 368 B
no cgroup, com swap zero e 6 848 MiB de VRAM total em uso. A parte OFF usou
15 990 554 624 B e os mesmos 6 848 MiB. O stop é de 20 937 965 568 B,
dentro do cap de 20 GiB. Mantido o restante pico ON, ficam 4 997 427 199 B
até ao último byte admissível. O orçamento independente do banco K353 soma
4 667 326 464 B de registos alinhados, 52 887 552 B em quatro scratch e
49 152 B de índice. A um custo de remap nulo, cada geração velha adicional
que continue retida **fora destes registos e scratch** acrescenta até
13 221 888 B. Quatro gerações distintas custariam 52 887 552 B adicionais.
As PTEs e as retenções simultâneas de leitores não foram medidas neste pedido.

O prefixo antes do POST contém 2 156 ofertas e 1 698 vítimas distintas.
A simulação partiu de banco vazio nesse prefixo, manteve sempre as últimas
353 ofertas distintas e perdeu as extras mais antigas ao esgotar o orçamento.
Durante T2 o espaço ficou por vezes disponível depois da primeira utilização
que teria valor. A extensão só conservou os pesos que sobreviveram ao corte
anterior; terminou com sete extras. O primeiro disco que serviu do excedente
foi o ordinal zero da camada 32 na call 74 de 5 tokens. Na call 75 foram
13 admissões, oito CPU. No decode foram quatro, uma CPU. As 16 primeiras
faltas cobertas estão agrupadas na série por call/tile. As últimas ocorreram
na call 101. A ordem de reserva identifica a necessidade; o tempo de chegada
dos bytes do candidato é desconhecido.

**FORMAL no domínio das vítimas oferecidas no prefixo observado e tags fixas.**
Mesmo escolhendo os experts com conhecimento de todo o T2 e concedendo-lhes
retenção gratuita depois do corte, o teto é de 300 admissões no orçamento
nominal: 188 de chaves CPU inicialmente partilháveis e 112 de até 35 chaves
inicialmente pagas. Com o pico físico de R0 mantido e toda a folga até ao
stop, sobe a 352 (188 + 164 de até 56 pagas). O teto concede ainda índices
gratuitos para as chaves inicialmente partilháveis. Os tetos por fase permitem
seleções diferentes e não se somam. Uma unidade que altere primário, tags,
fontes de T1 ou política de retenção exige outra prova.

**INCONCLUSIVE para poupança física e latência integrada.** Para converter
a conta em memória disponível, é necessário observar a duração das leases
(slot, geração), referências ao mesmo objeto/página e o pico conjunto de
backings, staging, PTEs e cgroup sob o novo layout. O ensaio C291 cobre o
primeiro handoff. [Fixture de manager](../manager/) · [Método](protocol.md)

O protocolo foi registado em `3f216f10`. Antes das contas, o código fixou
a fórmula exata do índice de host_cache e a fixture em `856e44d5`. A
reprodução da trajetória nativa, os dois planos e a reconstrução do prefixo
fecharam duas vezes em 0,94 s, com RSS de 83 872 e 83 796 KiB. Recibo
SHA-256 `40606cf47c0442fdf046272a0c85a1599f59997e5feab86fc15754c46ac7bb70`.
Zero leitura de pesos, GPU ou novos pedidos. Para reproduzir, executar em
checkout limpa com destinos exclusivos e comparar ambos os recibos
byte a byte.

```sh
python3 -IB "$STUDY/test_score.py"
timeout 120 prlimit --as=805306368 --cpu=118:120 --fsize=8388608 -- \
  python3 -IB "$STUDY/score.py" --family "$FAMILY_R02" --prefill "$PREFILL_PLAN" \
  --decode "$DECODE_PLAN" --new-output-dir "$NEW_OUTPUT"
```
