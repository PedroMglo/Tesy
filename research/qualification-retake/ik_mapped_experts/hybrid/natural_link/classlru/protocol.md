# LRU e ClassLRU após um primeiro turno completo

Antes das contas, fixar um desenho fatorial 2×2. A variável de política é o
planner nativo LRU ou ClassLRU do ik 7a5d90009b7ae55d3239cdd33244977c4eb10ff6.
A variável de capacidade é 128 ou 161 slots de peso nos mesmos 36 layers de
um único grupo, share=0, com a mesma ordem oficial e o mesmo top-4. LRU usa
n_tokens=1 como no hook, ClassLRU a largura real de selected por camada. Os
4 planos começam vazios antes da primeira linha do T1, com relógios e CRF do
init do pin, e continuam sem reset até terminar T2. O trigger da parte 106
precedeu o primeiro POST. O histórico de routing de uma eventual sonda anterior
fica fora do intervalo. As 1 440 entradas fotografadas pertencem ao R0.

Autenticar os dois turnos pela parte 106, pelo corte anterior ao segundo POST
e pela igualdade das 7 012 linhas ordenadas com a parte 97, usando os revisores
anteriores. Exigir 74 278 quartetos T1 em 86 calls, posição 0–2119, primeiros
2 043 tokens em nove calls, depois 77 unitárias. Reconciliar cada layer em
cada tile até à 35 podada, a ordem de rank e o total de chaves únicas por
sítio. Em T2 conservar 5+148 e as cinco tiles 32/32/32/32/20 da call 2, 46
passos unitários, primeiro conteúdo final após call 46, última amostra na 48.
Verificar o decode da LRU contra o resultado selado do grupo sem T1 que provou
convergência antes de terminar a call 5 tokens. Para ClassLRU a influência da
frequência e do estado anteriores ao trigger é desconhecida.

Apurar hits, fills, evictions, número de sítios, linhas e payload por fase
(T1 prefill, T1 decode, T2 prefill/tiles, primeiro final, decode total e ambos
os turnos). Cada fill paga 13 219 200 B de três matrizes. Distinguir o custo
de aquecer T1 do custo do pedido T2. Comparar a política dentro de cada
capacidade e a capacidade dentro de cada política. Uma redução sistemática
de fills nos dois relógios de T2 justifica testar a política nesse ponto; uma
troca entre fases fica condicionada ao seu preço. Se o payload serial sozinho
exceder o teto bruto otimista de 16 GB/s em 10 s ou 47/6 s, fechar a via
correspondente nesta condição. Abaixo do teto quantificar a margem e o custo
incremental admissível, sem converter o resultado em ganho de latência.
A meta depende também da aritmética, colocação e tempo do verdadeiro ik.
Executar o mesmo planner em duas leituras (originais e arquivo), com destinos
exclusivos e validação do mapeamento após cada plano. Nenhuma carga de modelo,
benchmark ou consulta ao dispositivo.
