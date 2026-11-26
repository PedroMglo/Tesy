# O mmap seletivo do ik preserva o cálculo C110 no 120B?

**GO para a pré-leitura CPU nestes dois cortes de exatidão. Efeito no tempo INCONCLUSIVE.** No 120B original, D0 e D1 produziram os mesmos 402 176 logits F32 bit a bit (201 088 por posição). Na posição 15, ambos deram o máximo único 3659. Após o teacher fornecido 976, ambos deram 3992. Todos os 216 intervalos de experts e bias ficaram mapeados no inode e nos offsets esperados; 61 073 326 080 B lógicos. Ambos fecharam as 108 matrizes, o pool, o contexto e o processo. GPU de cálculo zero, zero pedidos HTTP e zero saídas naturais. [Comparação completa e proveniência](physical-pair.json) · [Artefactos físicos reabertos](../../private_archive/part-131.json) · [Pré-registo](protocol.md)

| Medição no portátil | D0, procura | D1, quatro workers |
|---|---:|---:|
| GGUF residente no censo anterior à C118 (GB) | 3,640 | 11,627 |
| Carga e inspeção de 216 vistas (s) | 0,362 | 0,359 |
| Contexto 8192 (s) | 0,079 | 0,096 |
| Forward fornecido de 16 tokens (s) | 33,773 | 25,744 |
| Forward seguinte, 1 teacher (s) | 6,958 | 1,349 |
| Cleanup nativo (s) | 0,264 | 0,361 |
| Lançamento até saída observada (s) | 41,656 | 28,107 |
| Leitura do cgroup no dispositivo interno 259:0 (GB) | 46,878 | 37,134 |
| Leitura global do namespace interno (GB) | 46,910 | 37,251 |
| Pico de RAM cobrado ao cgroup (GiB) | 9,504 | 9,505 |
| Eventos high / max / OOM, swap de pico (B) | 72 107 / 0 / 0 / 0 | 52 510 / 0 / 0 / 0 |

D1 registou ainda 458 752 B lidos pelo cgroup em 8:0. Os pesos do modelo estavam no NVMe em ambos. As leituras do namespace incluem outros utilizadores, as páginas residentes podem estar cobradas a outro cgroup e o censo não identifica a interseção com os experts pedidos. As quatro threads adicionais foram observadas no D1. O seu tempo de serviço, as páginas que anteciparam e a poupança causal permanecem desconhecidos. A ordem fixa, a diferença inicial de 7,987 GB na cache e uma observação por braço impedem usar a diferença de tempos como ganho M4. A energia em joules permanece desconhecida.

**Comparação com os dois controlos independentes.** Cada uma das 201 088 palavras F32 difere na posição 15 e novamente na 16, tanto contra C110 como contra o stock e95426f. Os dois máximos únicos coincidem, as listas top-5 ordenadas divergem. Contra C110 os erros máximos absolutos foram 1,8560 e 1,3424, contra stock 2,6342 e 0,8164. A igualdade bitwise inter-backend falhou e faltava tolerância pré-calibrada para declarar paridade numérica. Os dois controlos históricos também diferem entre si. Para localizar uma divergência nos IDs das rotas há um gold separado C294 com 561 quartetos (camadas 0–34, posições 0–15, e camada 35 posição 15), já validado por duas testemunhas. Um callback exige controlo OFF/ON no novo backend. [Revisor de logits](review.py) · [Testemunha de routing C294](../../warm_routes40/canary/witness.py)

A família R02 preservou a admissão D1 interrompida antes do modelo quando a identificação de compiladores do estudo CUDA coincidiu com a C118. D0 já estava fechado e verificado. Uma identidade D1 exclusiva reutilizou os vetores D0 autenticados e cumpriu toda a C118. As duas reaberturas independentes do par têm o mesmo SHA-256. A próxima decisão de engenharia é testar a cache de experts CUDA na fixture pequena, com GPU residente de referência e falha de capacidade de controlo. A comparação causal de tempo em CPU exigiria controlar ou contrabalançar a residência inicial e repetir com o mesmo trabalho. O resultado qualifica só estes cortes e deixa R0, M3 e M4 nos estados do ledger. [Admissão D1](reopening-d1.md) · [Fixture híbrida](../hybrid/README.md)

## Primeira tentativa física

**R01, INCONCLUSIVE.** No Ryzen AI 9 HX 370, com o GGUF original no NVMe, a janela C118 passou em 60,146 s. D0 arrancou em E10. O loader declarou 2,14 GiB densos e 56,88 GiB de experts diferidos. A primeira inspeção da matriz gate da camada zero terminou com código 34, antes de criar o contexto. Zero forwards e linhas de logits. D1 ficou NOT_RUN pelo gate de D0. Duas reaberturas do recibo confirmam a falha. A medição não estima o desempenho da conversa nem o custo do prefetch. [Resultado por braço e hashes](physical-r01.json) · [Contrato dos braços](protocol.md) · [Referências e comparação](review.py)

**Causa identificada na inspeção.** A inspeção nativa comparava o dispositivo da VMA com o de `stat`. Uma testemunha posterior abriu o mesmo inode de 63 387 346 208 B e mapeou, só para leitura, os seus primeiros 4096 B sem tocar nos pesos. Btrfs reportou 0:56 em `fstat` e 0:38 em `/proc/self/maps`, inode 40127919 em ambos, VMA r--s com offset zero e caminho esperado. A verificação rejeitaria até essa vista comprovadamente legítima. R01 não guardou a entrada do mapa que levou à rejeição da matriz. A sua colocação efetiva exige nova prova. A correção confronta cada vista com uma VMA testemunha do FD autenticado, offset e permissões. [Precedente no Tesy](../../nvme_r0_gate/qualified_profile/authority.py) · [Qualificação sintética anterior](driver/README.md)

O observador mediu 0,509 s do lançamento à deteção da saída, pico de cgroup 148 705 280 B, zero swap/OOM e zero novas leituras nos contadores do namespace e do cgroup durante esse intervalo. A validação do encerramento encontrou o scope inativo. O censo anterior à C118 observou 888 759 de 15 475 427 páginas residentes (3 640 356 864 B) e demorou 1,137 s. Este valor refere-se a todo o ficheiro no momento do censo. A C118 e a passagem pelo loader não mediram o mesmo intervalo. [Definição do censo](cache-window.md)
