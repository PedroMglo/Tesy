# Dar um dos quatro ranks por concluído no primeiro decode da CPU0

**Receber gratuitamente a contribuição exata de e28 poupou 0,172 e 0,135 ms nas medianas dos dois blocos.** Este ganho local ficou aquém dos 0,812–0,954 ms por camada que o cenário do pedido requer em média para atingir 6 tokens/s, e dos 7,557–7,741 ms para o primeiro conteúdo final em 10 s. A forma medida foi uma só linha da camada CPU0 na posição 189, com e28/e24/e8/e16 já residentes. A relação entre o ganho nesta linha e o ganho nas restantes 24 camadas CPU permanece desconhecida. [Protocolo](protocol.md) · [Recibo e tempos dos 14 pares](receipt.json)

| Execução do FFN com oito threads C269 | Mediana do bloco 1 | Mediana do bloco 2 | Mínimo–máximo das 14 chamadas |
|---|---:|---:|---:|
| FULL, quatro ranks juntos | 0,659496 ms | 0,571198 ms | 0,557823–0,715190 ms |
| SERIAL, três ranks e e28 na mesma CPU | 0,697858 ms | 0,595404 ms | 0,585787–1,140754 ms |
| FREE, três ranks e linha e28 exata já disponível | 0,497240 ms | 0,427587 ms | 0,421646–0,601576 ms |
| FULL − SERIAL, diferença emparelhada | −0,036869 ms | −0,024206 ms | −0,496838 a +0,042591 ms |
| FULL − FREE, diferença emparelhada | +0,172145 ms | +0,135044 ms | +0,067688 a +0,254000 ms |

O intervalo inclui GEMMs, biases, SwiGLU, ponderação, soma dos quatro ranks em ordem e sincronização no regresso do grafo. Cada modo reproduziu as 11 520 palavras F32 ponderadas e as 2 880 palavras do FFN na paridade, no aquecimento e em cada uma das 14 medições. A substituição deliberada de e28 por e24 alterou 2 880 palavras do FFN e preservou os três ranks calculados. O cenário FREE concede a produção e entrega da linha de e28 previamente ao início do relógio. O custo de obter os quatro experts do armazenamento ficou na preparação comum. [Referência dos quatro ranks](../rank_cpu/README.md)

O R01 terminou antes da C118 por identidade incorreta do recibo NVML. O R02 passou a comparação inicial e a contraprova, mas falhou no aquecimento, antes dos relógios de desempenho. No R03 as quatro folhas de entrada ficaram protegidas como outputs do alocador nos três modos, e os seus digests foram conferidos fora de cada intervalo. A C118 durou 60,164 s; o scope terminou com retorno zero e pico de 173 506 560 B sob limite de 4 GiB e swap máximo zero. As duas observações periódicas de recursos do filho cobrem a execução agregada e não permitem estimar temperaturas ou energia por chamada. [Causa e correção](repair.md)

Para reproduzir, usar o supervisor e os argumentos de [rank_cpu](../rank_cpu/README.md) na revisão `03566a885843c0a7e96462f7745ce373696b013e`, com `rank_split/build.py`, `rank_split/profile.py` e `--rank-dir "$RANK_CPU_REFERENCE"` no lugar de `--gate-dir`. O recibo do monitor NVML CPU deve autenticar o diretório da biblioteca usada no scope. Preservar C55, C118 e novos destinos de build e execução.

**Antecedente consultado em 25 de novembro de 2026.** Apex divide os experts entre CPU e GPU segundo os tokens encaminhados a cada um e mede o tempo de transferência e cálculo. Os autores comparam no mesmo KTransformers com Fiddler, Post-Fetch e Mixtral-Offloading. Usam MMLU, três modelos BF16, uma RTX A6000 de 48 GB e um Xeon com 512 GB de RAM onde cabem os pesos. A sobreposição entre a computação CPU e o transporte/cálculo GPU é pertinente ao Tesy. A disponibilidade das matrizes no NVMe e o tempo até à primeira peça final numa única conversa exigem medições próprias. Aqui só se identificou o custo local de retirar e28 com a contribuição já disponível. [Apex, método e avaliação](https://arxiv.org/html/2610.23006v1#S4.SS1) · [Arquivo privado desta comparação](../../../private_archive/part-90.json)
