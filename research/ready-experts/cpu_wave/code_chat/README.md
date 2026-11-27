# O que justifica mudar o backend da conversa?

**NO_GO para uma reescrita integral com as hipóteses avaliadas. GO para conservar o pack de experts e a fusão CPU no executor Tesy para esta tarefa.** Em seis processos do portátil, o GPT-OSS-120B original completou doze pedidos com o mesmo histórico e os mesmos IDs. A função de código passou o validador nas seis execuções. Contra R0, a combinação adiantou o primeiro conteúdo da função em **4,075 e 3,862 s** nas duas ordens. Contra a mesma biblioteca com a fusão desligada, adiantou-o em **0,140 e 0,534 s**. Um executor C independente que anuncia suporte ao GGUF do target falhou a comparação de valores dos pesos. R0 `slots40-persistent` continua operacional. M3 PARTIAL e M4 NOT_MET. [Protocolo da conversa](protocol.md) · [Resultados físicos](code-chat.json) · [Operador independente](executor-result.json)

## O que recebeu a pessoa

O primeiro pedido avalia 2 043 IDs e termina naturalmente com 78 IDs, incluindo EOG. O segundo incorpora a resposta efetiva de cinco algarismos e pede a implementação de uma função Python que conta repetições consecutivas sem alterar a entrada. O target avalia **61 IDs novos** e reutiliza 2 044, num total de 2 105. Em cada braço gerou os mesmos 256 IDs incluindo EOG, com cap de 768. O cliente verificou as duas renderizações e as entradas oficiais. A revisão repetiu o validador funcional isolado C131 em cada função e conferiu os 255 passos seriais de decode. A igualdade demonstrada na conversa é a da trajetória greedy e da resposta funcional. Os 33 vetores completos de 201 088 logits finitos comparados no caso fornecido pertencem ao teste numérico anterior, com outro prefixo. [Trabalho fornecido nominal e de código](../supplied/README.md)

R usa a biblioteca C269 independente e o GGUF original no NVMe. P usa o pack C291 e a biblioteca CPU de W com a fusão desligada. W acrescenta a fusão das waves CPU totalmente estacionadas. Em todos os braços há um servidor Tesy com 40 slots por camada, quatro leitores, ub32, GPU12, oito threads, contexto 8 192 e o mesmo logging nativo, sem tracer de rotas. O relógio do primeiro final começa no envio do pedido. O fim do transporte precede o fim da validação. O scope inclui inventário, arranque, dois pedidos e encerramento do processo.

| Processo | T1 válido, s | T2 prefill, s | Primeiro final, s | Transporte, s | T2 válido, s | Decode, s | Decode, tok/s | Scope, s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 R | 80,967 | 10,658 | 32,782 | 76,084 | 76,105 | 65,416 | 3,913 | 223,982 |
| 2 P | 74,884 | 8,822 | 28,848 | 67,721 | 67,741 | 58,888 | 4,347 | 209,493 |
| 3 W | 70,310 | 8,865 | 28,708 | 67,235 | 67,255 | 58,360 | 4,387 | 204,478 |
| 4 W | 71,143 | 9,152 | 29,029 | 67,519 | 67,540 | 58,357 | 4,387 | 205,961 |
| 5 P | 75,066 | 9,633 | 29,563 | 68,097 | 68,121 | 58,452 | 4,380 | 210,495 |
| 6 R | 80,682 | 10,680 | 32,891 | 76,508 | 76,530 | 65,817 | 3,890 | 224,002 |

| Ordem | Referência de W | Ganho no primeiro final, s | Ganho até à validação, s | Ganho prefill, s | Ganho decode, s |
|---|---|---:|---:|---:|---:|
| R/P/W | R | 4,075 | 8,850 | 1,793 | 7,056 |
| R/P/W | P | 0,140 | 0,487 | -0,043 | 0,528 |
| W/P/R | R | 3,862 | 8,990 | 1,529 | 7,460 |
| W/P/R | P | 0,534 | 0,581 | 0,481 | 0,095 |

Os quatro contrastes passaram a proteção de +5% no decode T2 e na duração até à validação T1. No primeiro contraste P/W o prefill de W demorou mais 43,5 ms. O critério congelado de conservação do componente aplicava-se aos relógios do cliente e às duas proteções. Os dois pares com cache do SO em evolução natural dão o sinal observado nesta tarefa. A dispersão entre tarefas e o desempenho sustentado continuam por medir na mesma receita.

No nominal com **153** IDs novos, esta combinação já medira **17,689 s** até ao primeiro final, **17,938 s** até à validação e **5,357 tok/s** no mesmo segundo pedido. Para os alvos nominais faltam 7,689 s e 0,643 tok/s nesse pedido. No custo fornecido, o ganho total da combinação sobre R0 foi de 11,39% no nominal e 13,20% em código. O protocolo M3 continua a exigir as restantes tarefas e a sessão sustentada. A meta nominal de 10 s mantém o seu workload original. [Nominal e avaliação de custo](../README.md) · [Contratos de produto](../../../../results/c9-20260927T1441Z/usage-contract.json)

## Onde um motor diferente teria de ganhar

Nos dois W, o primeiro fragmento final de código foi produzido pela amostra **85 de 256**. Do despacho da tarefa ao envio do ID 84 para a avaliação seguinte decorreram **28,472 / 28,792 s** no relógio do próprio produtor. Ambos os eventos estão dentro do pedido do cliente. Conservando esse trecho, apagar todo o resto só poderia poupar **236 / 237 ms** até ao primeiro final. É um teto generoso para trocar apenas o invólucro HTTP. No nominal equivalente os tetos eram 177 / 186 ms. Reduzir segundos exige alterar a disponibilidade ou o custo do trabalho dentro do produtor. [Limite nominal e dependências de carga](../supplied/README.md) · [Cortes em código por processo](lookup.json)

**TRACE_DERIVED_CONDITIONAL.** O dispatcher compilado histórico e uma implementação independente reproduziram a regra que, a partir de um bigrama confirmado, propõe até dois IDs vistos anteriormente. Nos 255 avanços da sequência serial, o replay identificou 169 chamadas sem proposta e 46 chamadas de largura três. O target serial concorda com zero, um e dois IDs em 23, 6 e 17 blocos, respetivamente. São 40 IDs que poderiam ser confirmados e 215 chamadas se a verificação real reproduzir aquela sequência. Antes do primeiro final há 18 blocos e 20 IDs potencialmente confirmáveis. Os planos só usaram história já confirmada. O preço tem de cobrir também dispatcher, experts adicionais, contenção, confirmação e reposição das caches após rejeição.

| Processo | Máximo exterior ao produtor fixo, ms | Máximo médio por verificação para empatar o decode, ms | Decode se todos os blocos fossem gratuitos, s | Máximo médio para 6 tok/s em código, ms |
|---|---:|---:|---:|---:|
| 1 R | 268,1 | 474,2 | 43,601 | impossível |
| 2 P | 256,3 | 427,5 | 39,223 | 74,9 |
| 3 W | 235,6 | 425,3 | 38,794 | 84,2 |
| 4 W | 237,2 | 425,7 | 38,773 | 84,6 |
| 5 P | 246,0 | 427,8 | 38,774 | 84,6 |
| 6 R | 270,4 | 475,7 | 43,937 | impossível |

O cálculo conserva, por braço, o tempo do servidor exterior aos intervalos seriais substituídos. Inclui todos os erros no número de blocos cobrados. O preço até ao corte nativo do primeiro final tem outro denominador. Em W é 551,5 / 551,1 ms para cada um dos 18 blocos em média, mantendo o resto fixo. O relógio do cliente precisaria de uma nova medição para atribuir um ganho ao pedido. O diagnóstico de seis tok/s em código fecha esta via de proposta para R0 enquanto o restante serviço conservar estes preços. Com pack e fusão o custo médio máximo é **84,2 / 84,6 ms**. O ensaio nominal anterior do proponente N2/M2 atrasou o cliente. A verificação em código com W tem preço desconhecido. [Pré-registo do replay](lookup.md) · [Implementação e conservação dos intervalos](lookup.py) · [Especulação nominal medida no portátil](../../../qualification-retake/packed_nvme_manifest/server_profile/verified_block/server_reserve/causal_server/http/kv_width/natural/cpu_attention/target/http/family.md)

## O que aconteceu ao executar outro motor

No commit `9570410c` do executor C FiveTechSoft fizemos duas compilações independentes, escalar e AVX2, em cada reprodução. Testámos o mesmo GEMV que o seu forward chama nas projeções gate, up e down. A referência foi a biblioteca R0 qualificada. Cada entrada de base tem um único 1. Assim, a saída do produto escalar identifica um peso sem erro de ordem de soma. O slab inteiro de 4 406 400 B do GGUF coincidiu com o SHA-256 do índice C291. A entrada real foi os primeiros 34 bytes desse slab, que codificam 64 pesos. [Protocolo e fonte fixada](executor.md) · [Verificador](executor.py)

| Entrada de 64 pesos | Divergências na descodificação | Divergências no GEMV original | Divergências depois de permutar a entrada do mesmo GEMV |
|---|---:|---:|---:|
| Controlo constante | 0 | 0 | 0 |
| Fixture de ordem das coordenadas | 60 | 60 | 0 |
| Camada 0, expert 0, projeção gate do GGUF original | **52** | **52** | **0** |

Ambas as compilações deram essas contagens nas duas reproduções. O GGUF atribui os nibbles baixos às primeiras 16 coordenadas do bloco e os altos às 16 seguintes. O outro executor intercala os dois. A permutação isolou a causa nas entradas ensaiadas. **NO_GO para adotar diretamente esta revisão.** Uma segunda diferença surge na fonte da ativação. Com gate igual a 1 e up igual a 0, o SwiGLU desse executor devolve 0. A fórmula GPT-OSS com fator 1,702 e deslocamento +1 produz aproximadamente 0,846. Uma correção da ordem dos pesos abre a comparação da camada inteira, que teria de incluir bias, ativação, router, redução e estado. [Forward do executor C](https://github.com/FiveTechSoft/gpt-oss-120b/blob/9570410cab7e34bf7ac044559fc56dcdf4c7c195/engine/src/transformer.c#L307-L335) · [Modelo de referência GPT-OSS](https://github.com/openai/gpt-oss/blob/main/gpt_oss/torch/model.py)

## Um executor independente já pode substituir esta receita?

Em 27 de novembro consultámos o GooseInfer, revisão `c03c2ee9b93ee0709b9bde74bded6070bda8251f`. A matriz da release inclui Apex, Inkling e Bonsai. O registo de arquiteturas dessa revisão também não inclui GPT-OSS. Os autores já compararam 7 424 valores da desquantização escalar MXFP4 bit a bit e registaram o ensaio CUDA como fora do caminho exercitado pelo perfil Apex. **NOT_RUN neste target**. A prova que admite um ensaio é uma entrada executável para a arquitetura GPT-OSS com os seus pesos originais, seguida da comparação de uma camada routed contra a referência independente. O resultado qualifica esta revisão e esta oferta de produto. [Matriz da revisão](https://github.com/Endorpheen/GooseInfer/blob/c03c2ee9b93ee0709b9bde74bded6070bda8251f/tools/multimodel-release/release-matrix.json) · [Registo de arquiteturas](https://github.com/Endorpheen/GooseInfer/blob/c03c2ee9b93ee0709b9bde74bded6070bda8251f/docs/goose-migration/model-architectures.json) · [Fixture MXFP4 CPU](https://github.com/Endorpheen/GooseInfer/tree/c03c2ee9b93ee0709b9bde74bded6070bda8251f/experiments/EXP-2026-11-12-317-p2-13-mxfp4-decoder) · [Caminho CUDA exercitado](https://github.com/Endorpheen/GooseInfer/tree/c03c2ee9b93ee0709b9bde74bded6070bda8251f/experiments/EXP-2026-11-11-254-goose-cuda-dequant-mxfp4)

## Decisão e próximo discriminante

Conservar as melhorias compatíveis no Tesy. Um executor próprio merece investimento quando uma operação exata exigir uma fronteira que o executor atual impeça e a remoção dessa restrição produza margem no pedido completo. A entrega direta para a CPU e a fusão já funcionam na extensão GGML. A retenção causal e a antecipação avaliadas até aqui deixam o nominal acima do prazo. A diferença reproduzida no outro motor mostra concretamente que exatidão seria preciso recuperar para o substituir. Esta decisão aplica-se ao perfil HX 370 / RTX 4060 e aos mecanismos avaliados.

A experiência de menor custo para a proposta em código é capturar o primeiro bloco proposto no prefixo real e comparar a mesma profundidade confirmada em W serial e no verificador. Conferir primeiro os logits finitos, o KV, a rejeição e a continuação contra o target serial. Depois medir o bloco e o custo deixado nas chamadas seguintes. O preço de empate para a família é cerca de **425 ms por bloco em média**. Uma única posição caracteriza essa posição. A decisão sobre o pedido requer pesar os 46 blocos reais, repetir o par e proteger o nominal. Até lá, a ativação de N2/M2 em código está **NOT_RUN**. A receita de produção continua por qualificar. [Condição de reabertura da arquitetura](../../../../docs/architecture/0005-execucao-local-por-perfil.md)

## Proveniência e reprodução

Preparámos já as duas primeiras situações reais que distinguem rejeição e aceitação integral. Logo após **1 ID** confirmado, o verificador recebe três entradas a partir da posição absoluta **2 105** e o serial rejeita o primeiro ID proposto. Após **9 IDs**, começa na posição **2 113** e a trajetória serial coincide com os dois IDs propostos e fornece o bónus. A escolha exploratória é o primeiro exemplo de cada extremo no replay anterior. O gerador conserva os 2 043/78 IDs do primeiro turno, o prompt de 2 105 do segundo, o prefixo confirmado, os três inputs e as decisões seriais. O original e o arquivo produziram vetores idênticos nos dois casos. A fixture privada ocupa 38 665 B nas duas cópias. Para testar o ramo rejeitado será ainda preciso observar logits nas posições divergentes com uma referência serial alimentada com essas propostas, bem como KV e continuação depois de repor o estado. Os dois prefixos estão prontos para esse ensaio. [Geometria e hashes](prefixes.json) · [Gerador](prefixes.py) · [Selo privado](prefix-archive.json)

A família física partiu do PR #52 sobre o #51, com base integrada `293f5b18`. O pré-registo HTTP foi `53fa8ba4`, e a medição usou `1be14958`, árvore `6a0e2a22fee469ed0c02ef376c56b5bf41e47a53`. O protocolo do replay foi selado às 22:15 UTC, durante T1 do primeiro R e antes de qualquer T2. O campo histórico `measurement_tree` desse selo contém o commit físico. O protocolo e os programas de comparação foram registados em `1eb616c4`. O compilador C11 da fixture externa precisou do cabeçalho padrão de alinhamento em `0c16ed49`. [Selo antes de T2](lookup-freeze.json) · [Comandos, versões, custos e falhas](commands.json)

Os seis processos HTTP usaram AC, perfil performance, RTX 4060 Laptop de 8 188 MiB, driver 620.73.04 e GGUF original no NVMe interno. A janela C55 registou 61 amostras e pelo menos 26 563 227 648 B disponíveis. Os seis inventários C118 duraram mais de 60 s cada. A família demorou **1 475,383 s**, sob orçamento de 3 900 s. O máximo foi 15 771 541 504 B no cgroup com cap de 20 GiB e zero swap, 6 848 MiB de VRAM, 95,625 °C na CPU, 64,77 °C na GPU e 57,85 °C no NVMe. A integral da potência da GPU estima **12 980,5 J em 900,704 s** cobertos. A energia total da máquina e os bytes físicos do NVMe por token ficaram desconhecidos nesta campanha.

A primeira tentativa de confinar o operador externo parou na criação do scope, e a segunda na compilação AVX2 em C11. As duas estão preservadas. Nas identidades seguintes, com o mesmo protocolo numérico, cada reprodução demorou 0,55 s e usou até 120 648 KiB RSS. Os replays sem inferência demoraram 1,44 s cada, com pico até 261 924 KiB. Os programas reproduziram os resultados compactos byte a byte. O arquivo privado `ready-code-chat-20261127-01/part-01` conserva 259 ficheiros, 16 218 209 B e 62 destinos de links registados. Os prompts, os vetores de IDs e as respostas integrais ficam no portátil. [Manifesto do arquivo](archive.json)

```sh
unit=research/ready-experts/cpu_wave/code_chat
python3 -IB "$unit/review.py" --check "$unit/code-chat.json"
python3 -IB research/qualification-retake/private_archive/verify.py "$TESY_CODE_ARCHIVE" "$unit/archive.json"
part="$TESY_CODE_ARCHIVE/part-01"
family="$part/tesy-wave-code-chat-20261127-r01"
scratch=$(mktemp -d)
python3 -IB "$unit/review.py" --family "$family" --family-sha256 ff8cea095dfb1be9d322c1842b571d15009a0aaae55fdbdf0f71df24429152a3 --new-output-dir "$scratch/review"
cmp "$unit/code-chat.json" "$scratch/review/code-chat.json"
python3 -IB "$unit/prefixes.py" --family "$family" --replay "$part/lookup-r01" --new-output-dir "$scratch/prefixes"
cmp "$unit/prefixes.json" "$scratch/prefixes/receipt.json"
```

No portátil, os argumentos dos dois testes de arquitetura estão no registo de comandos. Usar uma identidade de scope e um diretório novos em cada repetição. A fonte externa autenticada está em `$part/independent-source`. A verificação pública em CI usa os recibos compactos e as fixtures sem modelo.
