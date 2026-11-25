# Quanto valem as 18 admissões cobertas pelas páginas partilhadas?

Pré-registo sobre a mesma agenda carry, 353 tags fixas e extensão causal de
vítimas T1. Reexecutar o estudo de capacidade e conferir por SHA todo o seu
recibo antes de usar as identidades. Exportar em memória os sítios guardados,
com call/tile/layer/wave/ordinal/expert e a correspondente geração/slot dos
planos autenticados. Requerer 1+13+4 admissões já decididas e 16 chaves.
Nenhuma outra chave, fase ou parametrização. Reutilizar os planos das partes
65 e 69, leituras e hashes do pack R/P, P/R nas partes 66 e 71, recibos de
parede da unidade conjunta e as duas superfícies do R0. Verificar recibos,
raws, ordens, geração e cobertura em cada uma das fontes. Combinar as duas
ordens de fase independentemente. [Captura de capacidade](../protocol.md) ·
[Relógios e restrições do pedido](../../../prefill_frontier/transport/joint/README.md)

**Decode.** No callback, cada job paga o READ do seu próprio sítio no pack
(zero para o banco) mais o SET C281 com homólogo; os SET inéditos retêm o
relaxamento do antecedente. O custo do callback é a maior cadeia. Refazer
o máximo retirando só o READ dos quatro sítios; conservar inclusive o SET
do job beneficiado. Reconciliar q=1 com o preço validado e manter o exterior.
O ganho em ns é o serviço no caminho crítico neste modelo de atribuição.

**Prefill.** Em cada call 5 ou 148 da fila ótima de quatro workers, publicar
worker-tempo total e retirado, união das leituras, parcela única dos READs
retirados, concorrência e despacho→drain. O relógio R ou P conserva a sua
própria ordem e respetivo retorno externo. Refazer uma simulação determinista
de quatro servidores idênticos, começando a zero em cada chamada. Servir
os jobs FIFO com o próprio preço de READ medido; agendar cada job na primeira
fila disponível. Comparar o modelo à parede observada em primeiro lugar, e
depois a mesma simulação com as 14 admissões retiradas. Este cálculo mantém
um preço que já inclui a contenção das outras leituras; o NVMe físico pode
reprecificar todo o serviço. Na hipótese de preços invariáveis, conceder
também como teto o somatório de todo o worker-tempo removido. Não converter
este teto condicional em limite físico.

**Decisão.** O máximo de `custo líquido adicional` admissível pela partilha,
formação de tags, PTEs, handoff, serving RAM e join, no cenário emparelhado,
é o ganho projetado do prefill mais o delta do caminho crítico de decode;
à igualdade não há aceleração. Informar os quatro orçamentos (ms por pedido),
o intervalo se apenas o teto condicional identificar margem, e a fração do
défice de 2,187–2,444 s comprado no cenário com todas as lacunas gratuitas.
Se até o teto for inferior ao défice, NO_GO para suficiência isolada com
os restantes preços fixos. Conservar a ablação de custos das capturas e
restauros de T1; esses serviços ainda não têm um preço medido no pedido.
Dois processos offline idênticos com inputs somente em leitura, até
120 s e 768 MiB cada, sem pesos, GPU ou processo de inferência.
