# Partilhar o backing CPU reduz sobretudo o trabalho de decode

**Com a mesma entrada causal, o oráculo de 1 262 lugares CPU chega a 414 leituras de disco no decode, contra 601 com 40 lugares por camada e 797 no carry causal anterior.** No prefill, partilhar capacidade entre camadas só reduz o mínimo de 864 para 859, dos quais 397 são leituras CUDA inalteradas. Ambas as fases da primeira comparação pertencem a uma única trajetória completa de T2 com o mesmo banco de T1. A escolha de vítimas usa o futuro e constitui um limite de capacidade. [Protocolo](protocol.md) · [Recibo por fase, âmbito e preço](evidence/receipt.json)

| Organização CPU; CUDA conserva o carry | Call 5 | Call 148 | Prefill | Decode | Total T2 | Prefill mínimo recuperando no fim os pesos do carry¹ |
|---|---:|---:|---:|---:|---:|---:|
| Carry causal C269 e banco fixo | 34 | 1 024 | 1 058 | 797 | 1 855 | 1 058 |
| P40, 25 pools de 40 e banco fixo | 34 | 830 | 864 | 601 | 1 465 | 888 |
| P1000, pool CPU comum e banco fixo | 34 | 825 | 859 | 459 | 1 318 | 859 |
| U1263, pool CPU incluindo o banco CPU, capacidade lógica | 34 | 825 | 859 | 414 | 1 273 | 859 |
| U1262, mesma organização com stride alinhado | 34 | 825 | 859 | 414 | 1 273 | 859 |

¹ O mínimo com reposição é um objetivo separado. A chamada de 5 continua a ter retorno mas nenhuma organização tem de restaurar os seus residentes nesse corte. Na saída dos 148, a restauração do conjunto CPU e do banco permite analisar o regresso ao carry. No layout unificado há 80 pesos comuns entre as duas estruturas a recuperar; materializar novamente essas duplicações no layout anterior poderia copiar 1 057 536 000 B. A igualdade dos membros não assegura slots, gerações, último leitor, preços de SET ou retomada dos 797 jobs. [Oráculo com 40 por camada e os diferentes cortes](../prefill_frontier/oracle/README.md)

## Autoridade e ocupação

Os 1 000 pesos primários de CPU estavam observáveis antes de T2. Das 353 vítimas seladas de T1, 263 pertencem às camadas CPU e 90 às camadas CUDA. No CPU, 36 já têm cópia primária. U começa, portanto, com 1 227 identidades distintas e espaço livre; não vai buscar ao passado as vítimas anteriores para o preencher. As páginas ocupadas, mais o orçamento das 263 entradas CPU do banco, somam 16 696 556 544 B antes de metadados. Cabem 1 262 registos de 13 221 888 B alinhados ou 1 263 payloads de 13 219 200 B se a organização permitir densidade crua. Os 90 registos mantidos em RAM para o consumidor CUDA, os 440 primários da GPU e os buffers dos workers não financiam lugares CPU adicionais.

Cada wave simultaneamente protege os experts que o target pediu. Preservámos os 40 slots lógicos da camada, a sequência causal de ranks para o primeiro e último consumidores e a geometria original. O backing pode faltar apesar da etiqueta lógica READY. U1262 pagou 152 leituras assim no prefill; todas cabem nas 462 leituras físicas CPU cobradas nessa fase. No decode, U pagou 158 leituras CPU e as mesmas 256 leituras CUDA. O ensaio não executa um allocator: um runtime precisaria de reconstituir as views das três matrizes, proteger o último leitor e não alocar simultaneamente outra cópia densa dos 1 000 pesos. O antecedente C294 agregava todas as 36 camadas num arranque ideal de decode; aqui a VRAM e a entrada temporal são restrições independentes. [Antecedente C294](../../../../../../cache_bound.py)

## O que permitem os preços físicos

Dos 158 READ CPU de U1262 no decode **todos têm duração de pack observada para a mesma identidade e o mesmo callback**. Foram suprimidos 383 dos READ CPU da população anterior de 797 no mesmo sítio. Conservar o exterior R0 e cada cadeia CUDA READ+SET, cobrar estes READ CPU por callback e dar custo zero ao remapeamento CPU produz **4,980354 e 4,990724 s**, ou tetos de 9,437 e 9,417 tok/s (47 saídas). O troço CUDA + exterior já custa 3,907862 e 3,909049 s. A duração do CPU de um novo grafo, incluindo page faults, pins e instalação das views, continua por medir.

Em cada um dos quatro cruzamentos, o prefill foi precificado ao débito útil médio de uma das duas travessias anteriores e o decode ao preço condicional do seu próprio testemunho. No U1262, **a agenda serial falha por 233–426 ms**. Com o pipeline ideal de duas tiles abre 366–558 ms para todos os custos omitidos. Com todas as lacunas gratuitas abre 725–918 ms. No P1000, o cenário serial falha por 433–638 ms. Esses débitos de prefill foram medidos com o trabalho anterior de 1 058 leituras; aplicá-los a outras chaves é uma sensibilidade, não um preço físico da nova população. O limite deliberadamente mais otimista, dando todo o serviço CPU do decode de graça e usando o prefill mínimo, ainda permite 656–839 ms de margem serial em U. Por isso, o resultado do testemunho não exclui todas as agendas aos preços do cenário. [Serviço de prefill e combinações medidas anteriormente](../prefill_frontier/transport/joint/README.md)

A LRU causal subsequente produziu 918 leituras no decode, contra 797 no carry conhecido. [Replay da política executável](causal/README.md) A paridade do grafo e a duração do handoff requerem gates separados. Nenhum pager, GPU, modelo ou launcher foi executado.

## Reprodução

Pré-registo `8e350120`, programa `ac6b9104`. Três testes verificam o mínimo em pequenas enumerações, pins, identidade por camada, reposição e a falta de backing num hit lógico. Duas execuções CPU, 1,11 s / 79 588 KiB e 0,97 s / 79 120 KiB, produziram recibos de 47 645 B idênticos com SHA-256 `097085db812f87c7d4a855edf231aa256066d340e4372a9ba9091ca9b4b1ceef`. A raiz de arquivo contém as partes 63, 65, 66, 69 e 71.

```sh
U=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/global_residency
OPENBLAS_NUM_THREADS=1 "$TESY_VENV/bin/python" -IB "$U/test_screen.py"
OPENBLAS_NUM_THREADS=1 "$TESY_VENV/bin/python" -IB "$U/screen.py" \
  --archive "$ARCHIVE" --new-output-dir "$NEW"
```
