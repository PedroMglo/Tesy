# Renovação concorrente do banco de pesos CPU

**GO para a renovação por referência no manager existente. NO_GO para atribuir a melhoria do quarteto ao token 11 do pedido nominal.** No portátil, manter o peso antigo legível enquanto o mesmo slot lógico recebia outra geração permitiu aos quatro workers entregar os novos pesos. No replay desde o primeiro turno, um dos quatro experts do token 11 ainda precisava do NVMe. Esse expert foi o último produtor nos dois registos. Antecipar só as outras três entregas adianta a barreira em **0 ns** com as restantes publicações fixas. [Prova física](evidence-20261128-r01/decision.json) · [Replay dos dois turnos](evidence-entry-20261128-r01/decision.json)

## Medição no portátil

No C291, os workers mapearam 1 000 slots lógicos em 1 252 registos físicos e serviram as três matrizes MXFP4 originais de cada expert através do mesmo buffer CPU partilhado. A reserva fixa a nova geração sob o mutex. O leitor conserva um ticket para o frame e época anteriores até o escalonador GGML terminar. Enquanto um destino está preso, o dispatcher entrega o primeiro trabalho seguinte executável. COPY e ID começam com o banco vazio e capturam a vítima quando há lugar. Nos hits, COPY faz três SET e ID publica o endereço já válido. Na saturação, COPY pode ter de materializar no staging do próprio worker e aguardar o último leitor. Há testes para dois leitores, reciclagem de um frame que ainda alimenta uma cópia e cancelamento antes do claim. [Patch nativo](runtime.patch) · [Controlador](cpu-weight-bank.h) · [Casos de saturação e cancelamento](check_bank.cpp)

Executámos quatro visitas impostas B,A,B,A aos quatro slots reais de CPU0. A contém os experts 47, 82, 75 e 52 e B as quatro vítimas observadas. O relógio de cada visita começa antes da reserva, inclui o cálculo do leitor antigo durante o serviço, o despertar, o remap e as três projeções dos quatro pesos recebidos. A tabela apresenta a soma das durações das duas primeiras e das duas últimas visitas. Cada célula dá a mediana de sete blocos na ordem DISK/COPY/ID e na inversa, em ms. [Protocolo congelado](protocol.md) · [Amostras e fases por submissão](evidence-20261128-r01/samples.json.gz)

| Braço | Preads / SET nas quatro visitas | Formação das duas primeiras, ms | Duas revisitas, ms | Processo até teardown, ms |
|---|---:|---:|---:|---:|
| DISK | 16 / 48 | 48,052 / 48,501 | 42,047 / 40,685 | 94,927 / 95,539 |
| COPY | 8 / 48 | 51,272 / 50,708 | 8,909 / 8,875 | 70,105 / 69,508 |
| ID | 8 / 24 | 51,996 / 50,594 | 2,078 / 1,919 | 61,391 / 59,370 |

Nas revisitas, a mediana das diferenças emparelhadas favoreceu ID por 6,632 / 6,815 ms contra COPY e por 39,741 / 38,891 ms contra DISK, sete sinais positivos em sete em cada ordem. Face a DISK, a formação custou mais 3,563 / 2,267 ms. Contando também a formação, a diferença emparelhada até aos resultados permaneceu favorável por 36,271 / 37,303 ms contra DISK e 5,259 / 6,767 ms contra COPY. O recibo tem os intervalos do cálculo antigo, publicação, disponibilidade, drain e teardown. [Pares individuais](evidence-20261128-r01/decision.json)

No teste de disputa, os três destinos independentes publicaram com o primeiro peso antigo ainda emprestado duas vezes. No braço DISK o quarto destino esperou o último release. Nos braços com retenção o quarto publicou antes do release sem alterar o resultado do leitor antigo. Houve 22 empréstimos e 22 devoluções em cada ensaio completo. Os 138 240 F32 das projeções coincidiram bit a bit entre DISK, COPY e ID. Endereçar as matrizes da vítima na última visita alterou 34 560 F32. Uma leitura curta de 4 096 B no retorno de pread deixou o expert 47 indisponível e os restantes trabalhos drenaram. [Resultados e controlos de falha](evidence-20261128-r01/decision.json) · [Auditoria independente dos F32 arquivados](audit.py)

O scope físico durou 66,833 s, dos quais 60,168 s em C118. O pico cobrado ao cgroup foi de 281 878 528 B, com zero swap. Os 16 553 807 883 B de arena designam a capacidade reservada. Esta fixture só toca os frames dos oito pesos. Os preads pediram 7 404 257 280 B ao pack, incluindo braços exatos, controlos de falha e aquecimento. Máximos amostrados de 50,75 °C CPU, 41,82 °C GPU e 36,85 °C NVMe. Energia e tráfego físico de NAND permanecem desconhecidos. [Comandos e hashes](evidence-20261128-r01/provenance.json) · [Build](evidence-20261128-r01/build.json) · [Medição](evidence-20261128-r01/physical.json) · [Arquivo privado](evidence-20261128-r01/archive.json)

## O que sobreviveu na conversa

P106 cobre as posições **0–2 119** do primeiro turno, 86 chamadas e 87 736 registos antes do segundo POST. Isto corrige a descrição de sufixo no protocolo. O estado anterior ao primeiro snapshot permanece desconhecido. O replay importou os 184 slots CPU READY e os 816 vazios desse snapshot, com o banco secundário vazio e a frequência inicial a zero. O mesmo controlador compilado e uma implementação independente por chaves concordaram em cada hit, captura e ocupação. As chaves e gerações nos 1 000 primários coincidiram com as publicações do target à entrada e à saída do segundo turno. P97 confirma o mesmo trabalho T2 e fornece um segundo relógio. [Protocolo prévio](entry-protocol.md) · [Verificador](entry.py) · [Proveniência e limites](evidence-entry-20261128-r01/provenance.json)

| Intervalo | Reservas CPU | Hits | Preads obrigatórios | Capturas | Hits que recorrem ao staging em COPY |
|---|---:|---:|---:|---:|---:|
| T1, prefill | 2 459 | 319 | 2 140 | 1 624 | 259 |
| T1, decode | 1 632 | 455 | 1 177 | 1 310 | 455 |
| T2, 5 tokens | 40 | 14 | 26 | 34 | 14 |
| T2, 148 tokens | 768 | 236 | 532 | 593 | 236 |
| T2, decode até ao primeiro conteúdo final | 773 | 233 | 540 | 630 | 233 |
| T2, cauda | 13 | 1 | 12 | 8 | 1 |

O banco chegou cheio a T2 e produziu 484 hits. A inicialização histórica com 227 pesos produzia 469. Foram ganhos 53 hits e perdidos 38, incluindo o expert 52 da chamada 11. Considerando todas as primeiras utilizações e mantendo as restantes publicações fixas, a soma do adiantamento das barreiras até ao primeiro final é 130,190 / 139,468 ms retirando apenas SET e 1 202,659 / 1 181,566 ms retirando também READ, em P97 / P106. São créditos locais condicionais. O trabalho libertado nos workers poderá mudar a fila, e as fases têm dependências de cálculo e CUDA. O maior grupo de prefill tem 13 hits entre 15 reservas, com as duas leituras dos experts 116 e 50 por pagar. O teste físico desse grupo foi especificado antes de o temporizar. [Resultado por fase, site e journal](evidence-entry-20261128-r01/decision.json) · [Protocolo da medição mista](mixed-protocol.md)

O resultado sustenta o NO_GO para reescrever integralmente o backend com este fundamento no HX 370. O melhor produto nominal medido é 17,689 s até ao primeiro conteúdo final, 17,938 s até à resposta validada e 5,357 tok/s. R0 slots40-persistent continua a referência operacional. M3 PARTIAL e M4 NOT_MET. Nesta unidade a RTX esteve presente e monitorizada, com zero kernels GPU, forwards integrais do 120B e pedidos HTTP. Para uso em produção falta adquirir e devolver os tickets no grafo integrado, incluindo cancelamento, e verificar KV, logits, recursos e tempos da mesma receita no cliente. A dependência que justificaria outro backend é uma espera relevante para o cliente que sobreviva à melhor intervenção admissível no caminho existente. [Decisão de arquitetura](../../../../../../../docs/architecture/0005-execucao-local-por-perfil.md)

## Medição do prefill com duas faltas obrigatórias

Na quinta tile da chamada de 148, o binário já qualificado do serviço em grupo leu do NVMe os experts 116 e 50 e serviu os 13 pesos retidos. No recorte das 20 posições, cada controlo acertou nos 54 hashes das matrizes e nos 19 ranks ativos. Os 61 ranks estacionados conservaram o ID −1. Atribuir ao expert 63 outro endereço alterou exatamente um rank em cada registo. O preço até o consumidor inclui as publicações, a barreira e o despertar. [Pré-registo](mixed-protocol.md) · [Dez submissões exatas e 112 medições de preço](evidence-mixed-20261128-r01/decision.json)

| Registo | Ordem | DISK, ms | COPY, ms | Só 63 por referência, ms | Todos por referência, ms | Diferença emparelhada só 63 − todos, ms |
|---|---|---:|---:|---:|---:|---:|
| P97 | Direta | 128,375 | 122,387 | 121,392 | 121,383 | −0,024 (3/7) |
| P97 | Inversa | 127,741 | 122,100 | 121,409 | 121,398 | +0,011 (6/7) |
| P106 | Direta | 105,239 | 96,609 | 95,694 | 95,635 | +0,059 (5/7) |
| P106 | Inversa | 105,667 | 96,584 | 95,669 | 95,626 | +0,043 (5/7) |

**INCONCLUSIVE para acrescentar as outras doze referências à de 63 neste regime.** Contra COPY, servir os treze por referência adiantou o consumidor nos 28 pares com medianas de 0,708–0,992 ms. Contra DISK as medianas foram de 6,272–10,041 ms. O scope durou 79,249 s incluindo 60,170 s de C118, com pico de 758 583 296 B, zero swap e 10 577 510 400 B pedidos ao pack. As duas reservas obrigatórias, a contenção e a barreira fazem parte do preço. O ensaio conserva a hora de despacho de cada producer da observação anterior. Todas as reservas foram aceites nos primeiros 20 µs, e o despacho do expert 63 só se tornou permitido aos 121,295 ms em P97 e 95,527 ms em P106. [Amostras](evidence-mixed-20261128-r01/samples.json.gz) · [Recursos e proveniência](evidence-mixed-20261128-r01/provenance.json) · [Arquivo privado](evidence-mixed-20261128-r01/archive.json)

A partir da raiz do checkout, a validação pública usa apenas CPU e um compilador C++20.

```sh
D=research/ready-experts/cpu_wave/frame_lease/group_service/shared_owner/renewal
python3 -IB "$D/run.py" check "$D/evidence-20261128-r01"
python3 -IB "$D/entry.py" --check "$D/evidence-entry-20261128-r01"
python3 -IB "$D/mixed.py" check "$D/evidence-mixed-20261128-r01"
```
