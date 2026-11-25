# Cache de segunda linha na RAM durante o segundo pedido real

Fixado antes de abrir quaisquer resultados PFJ1 de conversa. O primário R0 mantém
a agenda de reservas, quatro workers, 40 slots por camada e os três SET por
geração. Começar no trigger com L2 vazia. Só uma publicação de uma geração
servida depois do corte fornece conteúdo elegível. Não promover um residente
primário à L2 por mera observação. C135 no pedido natural obteve 40/1077 hits
de decode com 3 GiB globais e LRU. C294 com trabalho fornecido fechou frequência
e LRU no critério de 20% dos 32 passos. Mesmo a L2 fria após P, ilimitada e
gratuita no replay temporal C295, ficou aquém de 6 passos/s. O dual_store
comparou a origem USB/NVMe da mesma leitura. Nenhum deles identificou o
piso das gerações realmente necessárias no prefill natural C281/NVMe a partir
do descritor observado e dos seus estados no trigger.

## Pergunta e decisões

Só usar um par OFF/ON que tenha passado o contrato completo do supervisor da
conversa, incluindo as trajetórias, o journal selado, o FD e a geometria
5+148 e 46 avaliações posteriores. O resultado é condicional à ordem observada
de dispatch/publicação e aos critérios existentes da conversa. Recalcular os
dois orçamentos do braço ON (47 saídas conforme M4 e sensibilidade favorável
de 46 avaliações). Manter 4,5 GB/s decimais como cenário sustentado.

O piso de volume inclui cada identidade (camada,expert) com geração criada
no prefill e exigida por uma barreira de consumo no prefill. Com o primário
fixo, se o primeiro serviço desta chave desde o trigger for uma releitura de
um residente inicial entretanto expulso, ainda terá de a entregar. Deduplicar
essas chaves, conceder todos os LOADING já em curso à entrada e conceder custos
de armazenamento, cópia, lookup e contenção nulos ao piso. Cada identidade
obriga ao menos a um payload completo dentro do intervalo de serviço do prompt
(origem depois da entrada, consumidor antes do retorno). Verificar também o
número de chaves que elevam este piso acima do piso de experts inicialmente
ausentes do estudo principal; uma chave nunca entregue a uma barreira no
prefill não pode aumentar este piso. O intervalo inclui o tempo entre chamadas.
A hipótese de banda e os relógios condicionais da comparação são os do protocolo
da conversa.

Se até esse piso exceder o orçamento inclusivamente a 46, emitir
`NO_GO_COLD_HOST_CACHE_FIXED_PRIMARY_VOLUME`; se só exceder o de 47,
registar a dependência do denominador. Para preservar a hipótese de política
causal explícita, os hits LRU têm ainda de satisfazer o crivo histórico
de 20% das reivindicações no decode desta trajetória, além da condição de
volume de prefill da política e da admissão de RAM no braço observado.
Um sinal favorável abre no máximo uma fixture de cópia/lookup. A conversa
de código e os controlos de custo continuam necessários a uma decisão de produto.

## Memória e política causal

Cada carga tem três componentes de 4 406 400 B. Um slot da L2 contém
13 219 200 B de payload com stride alinhado de 13 221 888 B. Na falta, copiar
cada componente em staging antes de ser reutilizado pelo pread seguinte num
dos quatro novos slots de montagem (um por worker). Publicar as três juntas
e trocar índices com a vítima sem recópia. Cobrar este material também em
inserções inúteis. No hit, fixar a entrada da reivindicação à publicação,
copiar o triplo para o staging original e manter a cópia ao primário (CPU ou
CUDA). Reivindicações concorrentes consultam no mutex pela ordem PFJ1.
Evicção LRU por consulta bem-sucedida/publicação; se todas as vítimas estão
fixadas, fazer bypass. O limite ilimitado permite todos os hits temporalmente
elegíveis, não autoriza uma implementação desse tamanho.

Além de (K+4) strides, reservar um vetor direto 36×128×4 B, 4 KiB de
controlo e 64 B de etiqueta por slot incluindo os de montagem, arredondando
o total de metadados a 4096 B. K=0 é R0 sem custos adicionais. Fixar K=239
(3 212 959 744 B dentro de 3 GiB) e K=353 (4 720 263 168 B). E20 tem cap
20 GiB e paragem 19,5 GiB. O C270 R0 teve pico de 15 859 171 328 B e o
C281 de 16 191 946 752 B; reservar ainda o journal completo de 25 165 888 B.
O pico de produção pode variar; confrontar cada custo com o pico contemporâneo
maior de OFF e ON, sem somar o journal duas vezes quando já estiver no pico ON.
Um K sem folga é inadmissível; não o reajustar. Um estimador de capacidade
não autoriza alocação física.

Relatar por fase/tier os hits, misses, bytes do pread original evitáveis,
payload de admissão e entrega, cópias para o primário e admissões não usadas.
O contador do FD não mede NAND; contabilizar bytes não identifica tempo de
parede poupado. Se faltarem eventos ou autenticação, registar NOT_RUN/FAIL e
preservar. Só replay CPU, até 120 s/512 MiB, saída nova até 1 MiB. Nenhum
peso ou GPU. [C135](../../../../C135-C136-SLOTS40-RESIDUAL-DECODE-20260929.md)
· [L2 C294](../../../l2_read_admission/README.md) · [Teto temporal](../../../l2_critical/README.md)
· [Dois SSDs](../../../dual_store/README.md)
