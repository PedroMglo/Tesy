# Contribuições individuais dos quatro experts no primeiro decode CPU0

**As quatro contribuições capturadas recompõem bit a bit os 2 880 F32 do FFN de C127/C270.** É possível substituir a contribuição de e28 por uma implementação candidata e localizar a primeira divergência antes da soma final. A captura abrange CPU0, posição 189, ranks lógicos [28,24,8,16], slots [3,14,6,35] e gerações [6,6,5,4]. [Recibo e SHA de cada linha](receipt.json)

| Verificação | Resultado |
|---|---:|
| Oito tensores com quatro linhas de 2 880 F32 | 92 160 valores finitos |
| gate/up/down + bias do ID lógico | 34 560/34 560 palavras iguais |
| down com bias × peso individual do router | 11 520/11 520 palavras iguais |
| Soma `(((c0+c1)+c2)+c3)` contra o FFN externo | 2 880/2 880 palavras iguais |
| Ativação SwiGLU de e28 convertida em Q8_0 para a projeção down | 3 060/3 060 bytes iguais à recomputação independente |

O grafo usou as 24 componentes esperadas. Os callbacks observaram as multiplicações, os consumidores dos biases, a ativação e os quatro produtos finais. As tabelas expõem a saída observada do SwiGLU; a prova independente de aritmética desta captura cobre os produtos pelo router, a requantização de e28 e a redução. A fotografia pertence à trajetória de primeiro decode C270. A integração no pedido completo e o custo de serviço continuam em aberto. [Protocolo](protocol.md)

O ficheiro privado `ALIAS/rank/weighted.f32` contém as quatro contribuições contíguas, 46 080 B, SHA-256 `d80c7ba29c304d76099cf7dd28cfe58f365f919cc494ea247507614097c44a4b`. A gate pré-bias de e28 reproduziu `756c8384…1db3`. A linha seguinte, e24, tem SHA-256 `90709cf4e526cab2356d3e14114ac46dfff59528a5e865afe7b4b591aeeea9c1`. O ficheiro `down-rank0.q8` tem SHA-256 `615c73878e6fe04563c0600767aaff8449ad07e31bdb5f37c28b0b08bbdb0e28`. Estas três identidades permitem conferir a contribuição proposta, o dono alternativo após o remap e a entrada do down. Os raws contêm dados derivados e permanecem no arquivo privado.

A checkout de medição foi `7d42bab311c595f648e8cdd36d616fad39ebc8e3`. A C118 durou 60,168 s, o pico do scope de 4 GiB foi 170 135 552 B, e o swap permaneceu em zero. Houve uma única execução do grafo, com quatro registos do pack (53 035 008 B) e todos os workers encerrados. O supervisor conserva o tempo global do filho, que inclui a autenticação das componentes, as observações, o I/O e o cálculo.

O comando de build e o scope usam os mesmos argumentos da [referência CPU de e28](../cpu/README.md). Executar `rank_cpu/build.py` e `rank_cpu/profile.py` em destinos novos; acrescentar ao segundo `--gate-dir "$PHYSICAL_GATE"` com a referência física selada em `34f504b177c8878290513a8aa45d725cf54eae5915ba9f351579f503b5dd2ca7`.
