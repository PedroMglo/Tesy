# Quanto custa antecipar os experts desta conversa no NVMe interno?

**NO_GO para a emissão conjunta escolhida e para a entrega bloqueante de controlo neste regime.** Nos 44 passos anteriores ao primeiro conteúdo final, só as leituras da emissão conjunta demoraram 11,714 e 11,896 s. A meta para a pessoa é 10 s desde o início do pedido, incluindo o prefill. O teste deu ao leitor todos os offsets do passo à entrada, inclusive os que o router real só revelaria depois. A conclusão física aplica-se a este pack, esta agenda drenada de quatro leitores e este histórico. [Pré-registo](protocol.md) · [Observações e telemetria](evidence-20261128-r01/observed.json) · [Avaliação dos 32 braços de cliente](evidence-20261128-r01/grade.json)

| Ordem física | Leituras em 46 passos | Volume alinhado | Tempo de I/O nos primeiros 44 passos | Tempo de I/O nos 46 | Primeiro final projetado | Decode projetado para 47 IDs |
|---|---:|---:|---:|---:|---:|---:|
| D1, só procura | 788 | 10,419 GB | 3,726 s | 3,816 s | 11,433–11,770 s | 7,529–7,608 s |
| H2, previsão e procura | 2 662 | 35,197 GB | 11,896 s | 12,550 s | 16,010–16,279 s | 12,550 s |
| H3, previsão e procura | 2 662 | 35,197 GB | 11,714 s | 12,397 s | 15,828–16,097 s | 12,397 s |
| D4, só procura | 788 | 10,419 GB | 3,734 s | 3,825 s | 11,433–11,770 s | 7,529–7,608 s |

**MEDIDO.** D e H leem os mesmos 788 registos obrigatórios. H antecipa 352 desses registos e pede mais 1 874 que ficam sem consumidor. Os tempos do leitor somam grupos de até quatro READ submetidos por `io_uring` e aguardados até à última conclusão. O volume dividido por este tempo deu 2,724–2,731 GB/s em D e 2,805–2,839 GB/s em H. Cada passo conserva a fronteira do retorno. O despacho e as verificações no host constam no segundo relógio de cada passo. A paridade integral anterior aos quatro braços conferiu 3 462 matrizes MXFP4 em 1 154 registos. As leituras cronometradas conferiram 62 100 amostras de bytes. As chaves referem-se às rotas reais confirmadas pelo 120B. [Plano, leitor e limites de recursos](protocol.md)

**TRACE_DERIVED.** Cada linha combina a sua leitura física com os dois journals, os dois preços de cálculo residente e os dois braços do cliente da mesma trajetória nominal. A conta concede a sobreposição máxima em cada passo e mantém as cópias no serviço residual. Em H, mesmo oferecendo todo o cálculo de decode, o tempo físico das leituras já determina o corte. Em D, as leituras sozinhas deixariam um primeiro final de 7,840–8,117 s com o prefill modelado e o exterior do cliente. A espera de cada camada pelos pesos e cópias eleva esse valor a 11,433–11,770 s. A diferença localiza uma oportunidade para antecipar trabalho obrigatório com poucos bytes desperdiçados. A disponibilidade de cada expert no consumidor e a contenção com cálculo continuam por medir. [Preços e ablação de serviço por camada](../../service.md)

A RTX estava disponível e sem processos de inferência. A campanha durou 43,812 s para o leitor completo, incluindo 11,156 s de verificação prévia. Pediu 106 489 085 952 B ao pack no NVMe interno. O contador do dispositivo inteiro registou 106 489 102 336 B de leitura durante a janela. O pico de memória do scope foi 112 340 992 B, com zero swap. Máximos de 59,125 °C na CPU, 46,07 °C na GPU e 50,85 °C no NVMe. A potência amostrada da GPU em repouso corresponde a cerca de 133 J. A energia total do portátil é desconhecida. Houve zero forwards novos. A primeira preparação terminou no inventário Git por falta de um thread sob o limite de memória. O arquivo guarda a falha e a preparação concluída com um thread no processo seguinte. [Proveniência, comandos e orçamento](evidence-20261128-r01/provenance.json) · [Arquivo privado](evidence-20261128-r01/archive.json)

A reprodução pública requer Python e a árvore deste PR. Os dois primeiros comandos confrontam as previsões individuais e o certificado de todos os limiares com os seus recibos. O último reavalia as leituras físicas sem abrir o modelo.

```sh
d=research/ready-experts/verifier_wait/forecast
python3 -IB "$d/price.py" --witness "$d/evidence-20261128-r01/witness.json.gz" --check "$d/evidence-20261128-r01/receipt.json"
python3 -IB "$d/joint.py" price --scores "$d/evidence-joint-20261128-r01/scores.json.gz" --check "$d/evidence-joint-20261128-r01/receipt.json"
python3 -IB "$d/io/grade.py" --observed "$d/io/evidence-20261128-r01/observed.json" --check "$d/io/evidence-20261128-r01/grade.json"
```

A reexecução completa do leitor precisa do pack e índice íntegros, dos raws de T1/T2 e S e de passar novamente a janela de recursos C55. Os comandos históricos citam os destinos selados. Cada nova campanha recebe outros destinos e recibos. O teste de código, a sessão sustentada e a qualificação de produto desta política ficaram NOT_RUN. O melhor turno nominal já medido mantém 17,689 s e 5,357 tok/s. [Conversa natural e controlos](../../../cpu_wave/README.md)
