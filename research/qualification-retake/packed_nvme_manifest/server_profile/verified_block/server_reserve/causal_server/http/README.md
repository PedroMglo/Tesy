# Primeiro bloco especulativo da conversa no portátil

**NO_GO para o binário avaliado.** Um pedido HTTP real chegou à primeira proposta de dois tokens do T1. O servidor abortou na construção da atenção da camada 25. O binário promovido da fixture curta ainda exigia exatamente 256 células de KV nessa camada. A revisão de integração devia ter detetado esta restrição. Nenhum bloco terminou. A conversa ficou sem conteúdo final validado e sem medição de tok/s. O melhor T2 emparelhado mantém 18,313 s e 5,361 tok/s, M3 PARTIAL e M4 NOT_MET. [Protocolo anterior à medição](protocol.md) · [Resultados compactos](result.json)

| Braço previsto | Trabalho executado | Decisão |
|---|---|---|
| ON, pack e verificação | 1 processo, 1 pedido, prefill de T1 com 2 043 IDs, primeiros 20 IDs gerados iguais à referência independente | FAIL preservado e NO_GO para esta versão |
| OFF, mesma biblioteca serial | 0 pedidos | NOT_RUN após a falha |
| P, C291 histórico com pack | 0 pedidos | NOT_RUN após a falha |
| R, C269 original | 0 pedidos | NOT_RUN após a falha |

O dispatcher pediu a primeira verificação na posição 2 062. O processo usou reserva 3 e terminou com SIGABRT na asserção específica de L25. As três observações durante o silêncio do cliente já encontraram a thread em `do_coredump`. O journal do sistema confirmou o sinal. A medição identifica a asserção, o prefixo confirmado e o despacho. O número de células efetivamente passado a essa chamada ficou por observar. O cliente registou a falha da stream. O monitor não publicou o manifesto terminal. O encerramento do PID, da unidade e do listener foi confirmado separadamente. [Verificador sem modelo](review_failure.py)

A família durou 296,08 s incluindo inventário e encerramento. A janela C118 teve 61 amostras em 60,146 s. As 315 amostras durante a vida do PID cobrem 233,208 s, observaram um pico de 6 848 MiB na GPU e 15 943 753 728 B no cgroup, com zero swap no cgroup. Sem recibo final do monitor, energia total e máximos posteriores ficam desconhecidos. O dump transitório do sistema consumiu espaço no NVMe durante o fecho. O arquivo científico guarda os 37 ficheiros necessários ao diagnóstico em 1 837 524 B. Os originais e o arquivo reproduziram o mesmo resultado, SHA-256 `5882f5166cb88cf482147a9d26f10928e2d38c9ec4a40b5ef7c681dfba2f45db`. [Manifesto privado](../../../../../../private_archive/part-178.json)

O novo teste usa a largura real de K/V e da máscara em L25. Compara na GPU cada linha contra o operador stock serial, inclusive com janelas longas. A comparação de custo de produto só reabre depois da paridade. [Critérios e larguras congelados](kv_width/protocol.md)
