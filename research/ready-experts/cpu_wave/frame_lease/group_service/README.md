# Entrega de vários experts ao mesmo consumidor CPU

**GO para integrar a entrega por referência no serviço Tesy existente.** Na CPU0 do token de decode escolhido pelo protocolo, os quatro pesos já disponíveis em RAM chegaram ao consumidor em 0,084–0,087 ms. Copiar os mesmos pesos para os slots demorou 2,309–2,415 ms. A entrega dos quatro adiantou o consumidor nos 28 pares contra cada um dos dois controlos, mesmo escolhendo a alternativa individual mais rápida de cada bloco. No prefill, o benefício de acrescentar oito referências à do último produtor mudou de sinal. A medição qualifica a entrega depois de os pesos estarem disponíveis. O melhor pedido nominal medido por HTTP continua em 17,689 s até ao primeiro conteúdo final, 17,938 s até à resposta validada e 5,357 tok/s de decode. M3 PARTIAL, M4 NOT_MET. [Protocolo congelado](protocol.md) · [Pares e tempos absolutos](evidence-20261128-r01/decision.json)

A tabela mostra a diferença emparelhada de tempo até o consumidor verificar as gerações, em ms. Cada célula dá a mediana dos sete blocos na ordem direta e na inversa. Um número positivo favorece ALL. BANK mede as leituras diretas obrigatórias do NVMe e as cópias ainda necessárias. HANDOFF disponibiliza cada peso no instante relativo em que a leitura terminou no registo original. P97 e P106 observaram o mesmo trabalho em execuções independentes. ONE escolhe o mais rápido dos quatro experts individuais em cada bloco de decode. No prefill, ONE foi fixado antes do ensaio no último produtor observado, expert 63.

| Registo | Caso | Regime | COPY − ALL, ms | ONE − ALL, ms | DISK − ALL, ms |
|---|---|---|---:|---:|---:|
| P97 | Decode, 4 hits | BANK | 2,328 / 2,226 | 1,525 / 1,552 | 19,248 / 19,129 |
| P106 | Decode, 4 hits | BANK | 2,304 / 2,233 | 1,504 / 1,507 | 19,223 / 19,127 |
| P97 | Prefill, 9 hits | BANK | 0,723 / 0,922 | −0,018 / 0,012 | 6,254 / 6,363 |
| P106 | Prefill, 9 hits | BANK | 0,834 / 0,773 | 0,020 / −0,005 | 11,391 / 11,105 |
| P97 | Decode, 4 hits | HANDOFF | 1,349 / 1,285 | 0,522 / 0,591 | — |
| P106 | Decode, 4 hits | HANDOFF | 1,204 / 1,319 | 0,529 / 0,602 | — |
| P97 | Prefill, 9 hits | HANDOFF | 0,924 / 0,872 | 0,026 / −0,005 | — |
| P106 | Prefill, 9 hits | HANDOFF | 0,928 / 0,903 | −0,006 / 0,002 | — |

**Conteúdo e âmbito.** No decode o router pediu os experts 47, 82, 75 e 52. Na wave de prefill de 20 posições, 18 experts participaram. Nove foram servidos pelo banco, seis exigiram leitura e três já estavam no destino. Os quatro workers respeitaram a atribuição por job. A verificação de 48 execuções numéricas confrontou os três componentes MXFP4 originais de cada expert e a vista de cada rank, incluindo parking. Nos oito controlos de falha, apontar uma geração válida ao peso errado alterou exatamente a ocorrência esperada. O relógio de preço inclui despacho, entrega, publicação sob mutex e despertar. Há tempos separados para a última publicação e o drain. O ensaio começa com o banco preparado. Construir e renovar o banco, executar a camada, obter os logits e servir o cliente entram na qualificação da arquitetura. [Cenários](evidence-20261128-r01/scenarios.json) · [Amostras numéricas e temporais](evidence-20261128-r01/samples.json.gz)

**Recursos MEDIDOS no portátil.** Houve 560 execuções de preço avaliadas e 40 aquecimentos. O scope físico durou 108,058 s incluindo C118, com pico de 1 047 347 200 B e zero swap. As leituras pedidas ao pack no NVMe interno somaram 19 832 832 000 B. Os máximos amostrados foram 65,75 °C na CPU, 45,04 °C na GPU e 38,85 °C no NVMe. Energia e tráfego físico do dispositivo permanecem desconhecidos. Os pesos vieram do artefacto original. Houve zero forwards integrais, pedidos HTTP e kernels GPU. [Proveniência, orçamento, hashes e comandos](evidence-20261128-r01/provenance.json) · [Build](evidence-20261128-r01/build.json) · [Medição](evidence-20261128-r01/physical.json) · [Recibo do arquivo privado](evidence-20261128-r01/archive.json)

A partir da raiz do checkout, o comando seguinte reaplica o avaliador às amostras publicadas sem modelo ou GPU.

```sh
python3 -IB research/ready-experts/cpu_wave/frame_lease/group_service/run.py check \
    research/ready-experts/cpu_wave/frame_lease/group_service/evidence-20261128-r01
```

A decisão de reescrita integral permanece NO_GO neste perfil. A próxima escolha de implementação é se o tensor de cada camada pode ter um número fixo de frames próprios com o mesmo orçamento global de 252 retenções CPU. O custo de abandonar um banco partilhado depende dos hits realmente utilizados no percurso até à resposta. [Entrega e última utilização da camada routed](../README.md) · [Efeito condicional das 90 waves com vários hits](../group-result.md)
