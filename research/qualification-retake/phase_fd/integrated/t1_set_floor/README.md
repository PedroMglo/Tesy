# Quanto custam as entregas ao primário no segundo pedido?

**NO_GO para 353 entradas com as durações observadas de READ e SET, os quatro workers e as mesmas libertações por wave.** Mesmo escolhendo as melhores 353 de 1 698 vítimas de T1 com conhecimento do segundo pedido, o piso até ao primeiro conteúdo final sobe para **10,128999 s**. O crivo anterior, que cobrava apenas os READs indispensáveis, tinha 604,326 ms de margem. Incluir os SETs aumenta o melhor piso em 733,325 ms e deixa um défice de **128,999 ms**. A seleção ainda passa o crivo de volume de prefill: 9 002 275 200 B para uma disponibilidade condicional de 10 690 306 614 B no denominador M4. [Recibo](evidence/receipt.json) · [Reanálise da própria sessão](../t1_local/protocol.md)

## Sensibilidade ao preço das leituras

| Escala de READ | Capacidade inicial | Piso READ + SET | Folga máxima para todo o trabalho omitido | Chaves úteis em prefill | Piso do payload de prefill |
|---|---:|---:|---:|---:|---:|
| 1× | 0 | 13,004151 s | défice 3 004,151 ms | 0 | 11 262 758 400 B |
| 1× | 239 | 10,785656 s | défice 785,656 ms | 82 | 10 178 784 000 B |
| 1× | 353 | 10,128999 s | défice 128,999 ms | 171 | 9 002 275 200 B |
| 1× | todas as 1 698 | 9,702373 s | 297,627 ms | 524 | 4 335 897 600 B |
| 0,8× | 0 | 11,750395 s | défice 1 750,395 ms | 0 | 11 262 758 400 B |
| 0,8× | 239 | 9,977031 s | 22,969 ms | 82 | 10 178 784 000 B |
| 0,8× | 353 | 9,451459 s | 548,541 ms | 171 | 9 002 275 200 B |
| 0,8× | todas as 1 698 | 9,105081 s | 894,919 ms | 524 | 4 335 897 600 B |

O cenário de 0,8× encurta cada READ cobrado em 20% e mantém o SET ao preço observado. Com 353 entradas, a margem de 548,541 ms tem de absorver todos os custos omitidos que incidam no caminho crítico. Preparar estas 353 vítimas exigiria ter 4 666 377 600 B de payload correto antes de T2. O limite de 1 698 entradas concede todas as vítimas e excede a capacidade de ambas as L2 admitidas no crivo de RAM. O orçamento de volume dos 46 passos pós-primeiro token é 11 440 306 616 B. Em cada célula, a mesma seleção justifica tempo e volume. As seleções ótimas para os dois preços podem diferir. [Volume e memória](../host_cache/README.md) · [Critérios congelados](protocol.md)

## Serviço observado e relaxação

A conservação própria de T2 identificou 2 354 reservas. Das 1 918 reservas de procura, 1 894 tinham a procura e as três entregas na mesma callback inteiramente contida antes do primeiro conteúdo final, com margem exterior de 1 ms. Em todas as 1 894, a publicação ocorreu entre a entrada e o regresso da barreira. As 436 reservas de preload e as 24 reservas em callbacks exteriores ou a cruzar o corte recebem custo zero. O piso paga os SETs das 1 894 gerações e os READs das 875 primeiras gerações que ficaram fora da seleção. As 1 019 releituras restantes também são concedidas gratuitamente. O custo exterior às callbacks fica fixo em 6,008451991 s. Restam **3,991548009 s** para o serviço e todo o trabalho omitido.

| Origem e destino do slot | Gerações | Primeiras leituras | SETs | Worker-s de SET | Payload entregue |
|---|---:|---:|---:|---:|---:|
| Prefill · CPU | 532 | 375 | 1 596 | 0,315144 | 7 032 614 400 B |
| Prefill · CUDA | 295 | 192 | 885 | 0,349937 | 3 899 664 000 B |
| Decode antes do primeiro conteúdo final · CPU | 773 | 221 | 2 319 | 0,419162 | 10 218 441 600 B |
| Decode antes do primeiro conteúdo final · CUDA | 294 | 87 | 882 | 0,352034 | 3 886 444 800 B |

Somando os relógios dos workers, os 5 682 SETs ocuparam 1,436276950 worker-s para 25 037 164 800 B de payload. A soma das primeiras leituras, antes de qualquer seleção, foi 13,868315297 worker-s. O piso de **parede** em cada uma das 937 callbacks é o maior valor entre a cadeia serial de um trabalho e um quarto de todo o serviço que ficou nesse grupo. As janelas das callbacks são disjuntas. O preço de SET mede a chamada do worker ao backend no host. Atribuir o seu tempo à execução interna da GPU, ou deduzir tráfego NAND destes bytes, exigiria outros contadores.

Para testar um máximo por wave, o verificador força a seleção dos trabalhos de READ que o ultrapassariam. Se um SET ou uma leitura inamovível exceder o máximo, descarta essa hipótese. Distribui os lugares restantes pelas maiores leituras elegíveis e escolhe o menor piso entre todos os máximos possíveis. A DP distribui depois a capacidade entre waves e o verificador recalcula o valor com a seleção obtida. A diferença entre os ótimos com e sem SET permite quantificar a margem sem somar segundos de workers à latência do cliente. [Solver](screen.py) · [Enumeração exaustiva e falhas de componente/barreira](test_screen.py)

**TRACE_DERIVED.** Ambos os cenários concedem retenção perfeita para as chaves selecionadas, cópia da vítima, entrega ao staging e coordenação a custo zero. A reabertura exige demonstrar mudança nas durações, nos movimentos ou no instante de disponibilidade das primeiras procuras. O resultado refere-se ao T2 nominal da parte 40; o FAIL do transporte entre sessões permanece preservado. A prova física conjunta de M4 continua **NOT_MET**.

## Reprodução

Pré-registo em `e2b3ba86`, programa e testes em `2b3295a3`. Usaram-se as duas preparações autenticadas de T1 e as duas reproduções da avaliação local anterior. R01 fez 0,88 s/75 876 KiB de RSS máximo; R02, 0,87 s/75 420 KiB. Os dois recibos de 9 779 B são idênticos byte a byte, SHA-256 `3402d411f6baf85cfe82067bf106730776939b4822317e11dee40b3a654d0029`. Não houve novos forwards ou leituras de pesos. O verificador consulta os metadados de inode do GGUF.

```sh
STUDY=research/qualification-retake/phase_fd/integrated/t1_set_floor
python3 -IB -m unittest discover -s "$STUDY" -p test_screen.py
timeout 120s prlimit --as=536870912 --cpu=120 --fsize=1048576 -- \
  python3 -IB "$STUDY/screen.py" --part "$PART40" --model "$MODEL" \
    --inventory "$INVENTORY" --prepared-dir "$PREPARED" --score-dir "$LOCAL_SCORE" \
    --new-output-dir "$NEW"
cmp "$NEW/receipt.json" "$STUDY/evidence/receipt.json"
```

A [adenda com os dois preços de READ medidos no NVMe](nvme.md) obteve, para 353 entradas, um défice de 19,168 ms na primeira travessia e uma margem de apenas 6,596 ms na segunda.
