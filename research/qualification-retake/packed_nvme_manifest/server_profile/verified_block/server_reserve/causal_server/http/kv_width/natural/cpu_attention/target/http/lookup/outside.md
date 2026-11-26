# Quanto do prefill fica fora do serviço de experts?

**NO_GO para cumprir os 10 s só com esta família de cache e verificação se o trabalho fora do remap conservar a duração medida.** Em dois processos do 120B, depois de retirar todos os callbacks de experts, as chamadas de prefill ainda ocuparam 3,709 e 4,045 s. Qualquer banco fixo de 353 chaves oferecidas por T1 recebe no máximo 3,484 s para o prefill, mesmo no cenário que mistura os passos de decode mais rápidos entre braços e concede gratuitamente todo o serviço do prefill. A escolha retrospetiva que antes projetava 9,516 s passa a um mínimo condicional de 11,259 e 11,595 s. [Método congelado](outside-protocol.md) · [Relógios e limites](outside-result.json)

| Observação do prefill | Call de 5, duração / remap / restante | Call de 148, duração / remap / restante | Restante nas duas |
|---|---:|---:|---:|
| P97 | 0,457 / 0,305 / 0,152 s | 9,150 / 5,593 / 3,557 s | 3,709 s |
| P106 | 0,467 / 0,302 / 0,165 s | 9,454 / 5,574 / 3,880 s | 4,045 s |

Foram 35 e 1 296 callbacks por chamada nos dois journals. Cada duração vem da entrada ao retorno no próprio PFJ. O total exclui o intervalo entre as chamadas e quaisquer custos de cliente ou cleanup. A união dos callbacks e o seu complemento recompõem cada duração ao nanossegundo. A estimativa de prefill no cenário anterior já incluía um piso de I/O. Comparar os dois pisos requer o maior dos dois para permitir sobreposição.

| Preços dos passos individuais | Orçamento máximo do prefill antes / depois da cache | Menor primeiro final compatível com P97 | Com P106 |
|---|---:|---:|---:|
| SERIAL contemporâneo | 1,856 / 3,148 s | 10,560 s | 10,897 s |
| Menor observado em qualquer braço | 2,192 / 3,484 s | 10,224 s | 10,561 s |

**Como se obtém o crédito da cache.** Entre as 2 829 chaves oferecidas, qualquer seleção de até 353 serve, no máximo, 440 reservas nas 44 transições anteriores ao primeiro final. O máximo nas 46 transições do decode é 445. Conceder a cada uma das 440 a sua janela de 13 221 888 B a 4,5 GB/s produz 1,292807 s. O limite deixa escolher o melhor caminho de decode sem a obrigação de atingir 6 tok/s e deixa dar o crédito até a passos que esse caminho substitui. Ignora custos de cópia e de coordenação. A taxa e a poupança por hit pertencem ao modelo condicional das partes 194–197. Uma política que evite mais serviço exposto por hit ou mude a duração dos blocos exige novos preços. [Fronteira de decode](envelope.md) · [Seleção e sobreposição](offers.md)

**O que pode ainda mudar o resultado.** Mesmo com o crédito mais generoso falta reduzir pelo menos 224,295 ms no P97 e 560,954 ms no P106, ou obter tempo equivalente noutro ponto do pedido. Para o caminho retrospetivo específico, faltam 1,259 e 1,595 s. Na chamada de 148, 2,236 e 2,468 s das lacunas caem entre waves sucessivas da mesma camada CPU. Essa posição identifica onde procurar. Pode incluir nós de grafo, scheduler, espera e efeitos assíncronos. A fixture de uma tile residente encontrou 0,731–0,820 ms nas MMID das sete waves vazias e 13,400–14,134 ms na wave ativa. A pergunta seguinte é quanto dos intervalos exteriores do pedido ocorre depois de waves sem trabalho routed. A política operacional já evita dots estacionados na CPU. [Controlo residente e limites da atribuição](../../../../../../../../../../../../phase_fd/integrated/cpu_residual/resident_team/README.md)

As execuções originais e sobre o arquivo usaram a árvore limpa de `35bdff57a92047800311bd0e1223db364baca393`, demoraram 3,830 e 3,859 s, com picos de 104,1 e 102,1 MiB, zero swap, GPU e pedidos novos. O compacto reproduzido tem SHA-256 `168a3bf6ad5fcda1550c835334a902cd410bf544245fbbbb23718226e1f91052`. O replay usa o [comando da parte 196](joint.md) com `outside.py`, este commit e um destino novo. [Código](outside.py) · [Recibo de quatro ficheiros, 11 128 B](../../../../../../../../../../../../private_archive/part-198.json)
