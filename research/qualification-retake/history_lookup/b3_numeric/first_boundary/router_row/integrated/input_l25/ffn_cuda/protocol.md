# Que geometria da FFN permite ao target verificar três posições exatas?

Pré-registo de 26 de novembro de 2026, base Tesy `3d70bd9fdc38204508f2e1c00b277eed146b6bb3`. Na RTX, a execução completa já recupera a entrada da FFN, os quatro experts e os pesos da mistura de L25 nas posições 189–191. A saída diverge em 33, 29 e 109 dos 2 880 F32. A conversa nominal mais rápida chegou a 18,313 s e 5,361 tok/s. O verificador em bloco precisa de confirmar o cálculo do target e depois pagar o custo de cada grafo. [Ablação de atenção no modelo completo](../serial_reference/attention/row_operator/full_graph/README.md)

**Referências.** Reabrir integralmente a família AR da parte 165 e a família ON da parte 167 pelos respetivos recibos. Verificar a geometria real, a colocação CUDA, a identidade do GGUF do NVMe e o inventário C7. Exigir igualdade bit a bit das três ativações normalizadas, dos quartetos ordenados e dos pesos da mistura entre AR e ON. Usar como referências independentes as duas saídas capturadas no 120B. Abrir apenas os intervalos de gate, up, down e respetivos biases dos experts selecionados pelo target. Registar hashes, bytes e proveniência sem versionar payloads.

**Experiência e critério.** O pin C269 usa um remapeamento para uma única wave porque doze pares cabem em quarenta slots. Cada produto recebe o ID físico e cada bias recebe o ID lógico. No fonte CUDA, a fusão dos cinco nós de gate/up com biases e GLU exige o mesmo tensor de índices nos produtos e biases. O código de dispatch também distingue o número de posições. A alternativa mais forte é que a diferença surja na projeção down, na ponderação ou na redução, ou dependa de estado ausente na reconstrução. Manter MXFP4, biases F32 originais, SwiGLU OAI com 1,702 e 7, quatro ranks e os três adds esquerdos na ordem do target. Usar um banco físico de quarenta slots e tabelas de biases de 128 em todos os braços. Qualificar os controlos nas duas geometrias antes de interpretar a intervenção.

| Braço | Grafo CUDA e referência |
|---|---|
| A | Três grafos seriais com os mesmos operandos da chamada em cada posição. Exigir igualdade integral a AR. |
| B | Um grafo com três posições em todos os nós. Exigir igualdade integral ao ON integrado. |
| U | Dividir apenas up, gate, biases e SwiGLU por posição. Reunir antes de down e fazer o resto com três posições. Comparar com AR e B. |
| D | Calcular o primeiro grupo em bloco, dividir down e o seu bias, reunir antes de ponderar e reduzir. Comparar com AR e B. |
| S | Os dois grupos de projeções por posição, com ponderação e redução em bloco. Comparar com AR e B. |
| F | Uma FFN integral por posição dentro de um único grafo, recompor na ordem nativa. Exigir AR para admitir esta correção. |
| B-alt e F-alt | Mudar o posicionamento dos dez experts para outros dez slots, manter os mesmos bytes lógicos. Exigir os mesmos resultados de B e F. |
| Mutação | Somar 1 ao primeiro bias down do primeiro expert da posição 189. Exigir mudança apenas na primeira coordenada das posições que selecionaram aquele expert e pelo menos uma mudança. |

Autenticar a DSO CUDA, compilador, ELF, famílias, fontes e dependências. Omitir especulação sobre os IDs físicos que o observador não gravou. A e B diferentes da sua referência, ou falha de permutação ou mutação, dão INCONCLUSIVE. Com os controlos admitidos, um braço que reproduza todos os 8 640 F32 de AR admite a sua integração e uma nova comparação dos logits completos. Se nenhum reproduzir AR a variante tem NO_GO neste regime. Uma comparação por posição classifica os braços híbridos. O teste não mede tempo de produto ou de pipeline e não prova invariância para outras rotas, slots ou posições.

**Recursos.** Uma preparação em scope de até 3 minutos, 2 GiB RAM, zero swap, até 150 MiB de dados e build. Uma execução CUDA em até 60 s de processo, 1 GiB adicional de VRAM, 2 GiB de RAM, zero swap, 16 MiB de saída. No máximo um processo CUDA, zero forwards do modelo, zero pedidos HTTP. Verificar a política de recursos, AC e perfil performance, sensores e processo exclusivo de compute. Registar amostras antes, com o banco vivo e após o cálculo. Proveniência incompleta, não finito, violação de recursos ou erro nativo terminam a identidade. Rejeições e dados permanecem em destinos novos e privados. Congelar tudo antes de observar os braços. M3 PARTIAL e M4 NOT_MET.
