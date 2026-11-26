# Os ganhos de cache e layout persistem ao entregar os pesos à CPU e à CUDA?

**MEDIDO no portátil. GO para a fixture isolada do manager.** Nas quatro waves selecionadas do segundo turno, combinar a expulsão prioritária dos experts recuperáveis em RAM com o pack contíguo reduziu o tempo de serviço em **62,18% e 62,46%** nos dois processos. Com o pack já ativo, a mudança de política ainda retirou **22,52% e 22,04%**. Com a nova política já ativa, o pack ainda retirou **50,22% e 51,41%**. Os três contrastes tiveram sinal favorável em 4/4 blocos de cada processo. A qualificação da conversa continua em **M3 PARTIAL e M4 NOT_MET**. [Protocolo prospetivo](protocol.md) · [Recibo com todos os blocos, estratos, volumes e limites](evidence/receipt.json)

## Relógio de serviço

Cada célula serviu os mesmos 29 consumidores nas quatro waves, com quatro workers e o mesmo banco causal de 353 entradas. A e B usam LRU. C e D expulsam primeiro um expert recuperável no banco. A e C leem as três componentes no GGUF original do NVMe interno. B e D leem um registo contíguo no mesmo NVMe e encaminham as mesmas três componentes. O cronómetro inclui despacho, leituras e entregas requeridas, espera pelos workers e sincronização de GGML. A tabela dá a mediana de quatro somas das quatro waves, em milissegundos.

| Processo | A · LRU + GGUF | B · LRU + pack | C · Nova política + GGUF | D · Nova política + pack |
|---|---:|---:|---:|---:|
| P1, r02 | 125,016 | 60,761 | 95,365 | 47,446 |
| P2, r03 | 123,945 | 59,838 | 95,956 | 46,487 |

As percentagens são medianas das reduções relativas de cada bloco emparelhado. Em P1 a redução combinada variou de 61,70% a 62,62%, e em P2 de 62,21% a 63,05%. A interação em tempo, B + C − A − D, foi negativa nos oito blocos. As duas intervenções retiram em parte o mesmo trabalho. O efeito medido da combinação já inclui essa sobreposição. O controlo anterior tinha medido a entrega a buffers em RAM. [Controlo de transporte em RAM](../t1_primary_layout/README.md)

| Fase e destino | Consumidores | D face a A, P1 / P2 | Política sobre pack, P1 / P2 | Layout sobre política nova, P1 / P2 |
|---|---:|---:|---:|---:|
| Call de 148, CPU | 12 | 56,66% / 56,42% | 7,39% / 8,12% | 52,36% / 52,85% |
| Call de 148, CUDA0 | 9 | 62,40% / 62,96% | 28,51% / 28,26% | 43,74% / 45,99% |
| Decode, CPU | 4 | 64,65% / 65,28% | 28,79% / 26,98% | 48,01% / 50,20% |
| Decode, CUDA0 | 4 | 99,95% / 99,93% | 99,90% / 99,87% | 17,93% / −13,07% |

Na wave de decode CUDA, C e D acertaram nos quatro slots primários. Com zero leituras e zero SET, o último contraste mede a preparação da lista vazia e a sincronização, que demoraram entre 3,396 e 7,564 µs. C para D teve sinal favorável em 3/4 pares de P1 e 1/4 de P2. Os outros contrastes da tabela tiveram sinal favorável em 4/4 pares por processo.

## Bytes, validação e recursos

Os valores abaixo são por célula, numa passagem das quatro waves. FD representa os bytes devolvidos pelas leituras alinhadas. Banco e SET medem o payload lógico. Nas duas waves CUDA, a LRU contou quatro entregas de disco, zero de RAM e nove hits primários. A nova política contou duas de disco, três de RAM e oito hits primários. O payload de SET na GPU subiu 13 219 200 B por passagem. A instrumentação não contou tráfego físico do NVMe nem do PCIe. [Volumes por origem e por wave](evidence/receipt.json)

| Célula | Chamadas ao FD | FD (B) | Banco RAM (B) | SET CPU (B) | SET CUDA0 (B) |
|---|---:|---:|---:|---:|---:|
| A | 54 | 238 178 304 | 13 219 200 | 198 288 000 | 52 876 800 |
| B | 18 | 237 993 984 | 13 219 200 | 198 288 000 | 52 876 800 |
| C | 42 | 185 262 080 | 52 876 800 | 171 849 600 | 66 096 000 |
| D | 14 | 185 106 432 | 52 876 800 | 171 849 600 | 66 096 000 |

A passagem de aquecimento ABCD e os quatro blocos ABDC, BCAD, CDBA e DACB perfazem 20 células por processo. Antes do relógio, o runner prepara os hits primários e enche de 0xA5 os slots a servir. Depois da sincronização lê de volta as três componentes de cada consumidor e confere os 87 SHA-256 do plano em cada célula. Cada processo verificou 1 740 componentes. O revisor independente reconcilia os 87 hashes esperados, a cobertura, as contagens e os bytes dos journals. Os digests de cada readback foram comparados durante o ensaio e o journal conserva os totais por wave.

Por processo, a preparação e verificação dos ficheiros leram 767 152 128 B e o serviço leu 4 232 704 000 B, incluindo aquecimento. A fatia NVMe de 383 434 752 B já existia e foi autenticada. Houve zero escritas de pesos, zero forwards e zero avaliações FFN. Cada tier tinha três tensores MXFP4 de 2 880 × 2 880 × 40, com destinos WEIGHTS e intervalos disjuntos. Os buffers nativos ocuparam 528 768 000 B na CPU e 528 768 384 B na CUDA0.

| Custo ou recurso | P1 | P2 |
|---|---:|---:|
| Preparação e verificação inicial (s) | 1,746 | 1,650 |
| Inicialização GGML e buffers (ms) | 278,991 | 265,216 |
| Cleanup da fixture (ms) | 14,467 | 18,445 |
| Pico do cgroup (B) | 926 576 640 | 925 265 920 |
| Pico de VRAM total observado (MiB) | 608 | 608 |
| Máximos CPU / GPU / NVMe (°C) | 58,250 / 44,87 / 34,85 | 57,375 / 44,38 / 33,85 |

A C118 de cada processo recolheu 61 amostras em 60,166 / 60,180 s. O monitor de serviço recolheu 25 amostras por processo, com o mesmo provider NVML, alimentação AC, perfil performance, cgroup de 2 GiB, swap desativada no scope e teto local de 1 536 MiB de VRAM. O último snapshot ainda viu o contexto CUDA e 102 MiB totais de VRAM, após a libertação dos buffers. O relógio de cleanup termina nesse encerramento da fixture. A saída final do processo, a validação por readback e a energia integrada ficaram sem relógio ou contador dedicado.

## Cobertura da conversa e condição de avanço

**TRACE_DERIVED.** As quatro waves continham uma falta de disco a menos cada uma com a nova política. Na call de 148, o censo do mesmo T2 conta 1 296 regiões de remap, das quais 1 022 sem procura e 36 só com hits primários em ambas as políticas. Das 238 restantes, 32 reduzem as faltas de disco. As duas waves de prefill da fixture pertencem a essas 32. No decode anterior ao primeiro conteúdo final, houve 1 584 regiões. A nova política retirou faltas em 149 e aumentou-as em duas. Para repor os residentes no início do decode, a simulação cobra ainda 185 leituras de disco e quatro entregas de RAM em LRU, ou 172 leituras e 88 entregas na nova política. A seleção privilegia divergências de política. A fatia de 29 experts também aproxima fisicamente os registos no pack. O efeito do layout completo e o tempo do pedido exigem medições próprias. [Censo completo, fronteira temporal e amostra prospetiva](../t1_full_workload/README.md)

A próxima fixture deve medir o manager com publicação, pins, banco RAM efetivamente capturado e consumidores routed. Deve conservar um R0 contemporâneo, ablações por mecanismo e proteção do outro caso. A estimativa de cobertura mais ampla tem 42 estratos e 21 426 974 720 B de leituras previstas por processo no desenho fatorial completo, acima dos 8 GB desta unidade. A respetiva admissão, o ensaio de logits e primeiro decode, a latência até ao conteúdo final válido e a qualificação M3/M4 ficam em aberto.

## Proveniência e reprodução sem modelo

Protocolo selado em `165cc970`. A tentativa `tesy-native-sinks-physical-20261125-r01`, em `0a40a88d`, conserva **FAIL_PRESERVED**. Depois da inicialização, o monitor destinado a máquinas sem clientes de computação GPU recusou o próprio PID da fixture com 600 MiB. O recibo raw da tentativa, `receipt.json`, tem SHA-256 `b83930de106ada7cc649c98d103266cf2999dcdedd62ae815efdc5972a93be46`. O monitor corrigido verificou o UUID e o único PID autorizado no período ativo. O backend, o trabalho, a geometria, os limites e os critérios foram os mesmos nos dois processos medidos, em `64225cdf7a71d66e3276535c031d8eab024767e0`, árvore `5a8cdd8a9ec3908416d748e52d70d7a4faa3b693`.

A reprodução lê os recibos, o plano e os journals privados, incluindo os inventários e monitores. O mapa estático identifica as bibliotecas e o driver C269. O caminho C55 aponta para o recibo no diretório que contém também `resource-policy.json`. A saída tem de ser nova. No portátil, estes comandos usam os nomes originais. Para uma cópia arquivada, apontar as entradas para os diretórios correspondentes.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_native_sink
python3 -IB "$unit/test_native_review.py"
python3 -IB "$unit/review.py" \
  --first /tmp/tesy-native-sinks-physical-20261125-r02 \
  --second /tmp/tesy-native-sinks-physical-20261125-r03 \
  --plan /tmp/tesy-transport-victims-plan-20261125-r03/plan.json \
  --map /tmp/tesy-env49-static-r01/static-map.json \
  --ram-receipt /tmp/tesy-layout-combined-physical-20261125-r02/receipt.json \
  --c55 /tmp/tesy-layout-combined-c55-20261125-r01/receipt.json \
  --new-output-dir "$NOVO"
cmp "$NOVO/receipt.json" "$unit/evidence/receipt.json"
```

As duas revisões independentes produziram o mesmo recibo de decisão, SHA-256 `c70cb5b267cc26877f8d353c8cdb27c6f7334b392be6c9983ddbbad61e6f57fe`. [Programa de medição](measure.py) · [Implementação dos destinos](native.py) · [Revisor sem GPU](review.py)

O arquivo privado da unidade é a parte 46 de qualification-20261124-nvme-01. O manifesto SHA-256 b5a515ca1d71fced8f51257555aee849abbe3bdffab51c6826716e8601b91b48 cobre 20 ficheiros e 927 215 B. A reprodução a partir da parte 46, do plano e da C55 da parte 44, produziu o mesmo digest. Uma consulta NVML após a saída do segundo processo encontrou zero clientes de computação GPU.
