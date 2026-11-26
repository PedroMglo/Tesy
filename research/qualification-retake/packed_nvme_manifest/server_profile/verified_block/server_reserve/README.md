# Pack e bloco exato nas reservas usadas pelo servidor

**GO para a proposta causal numa conversa.** As sete execuções no GPT-OSS-120B MXFP4 original passaram. As bibliotecas C291 de produto, recompilada e candidata reproduziram o prefill e as cinco decisões greedy de C269 com os 189 IDs de entrada. A biblioteca candidata reproduziu também todas as distribuições consultadas, o KV e duas continuações nas três rejeições/aceitações provocadas. As distribuições contêm 201 088 F32 finitos. A âncora foi 410. As reservas efetivas de uma e três saídas coincidiram com o log do contexto. O cliente nativo conservou a sequência viva, sem observador. [Protocolo](protocol.md) · [Resultado por braço](result.json)

| Processo | Reserva | Agenda | Cargas do pack após prefill e no fim | Duração do processo (s) |
| --- | ---: | --- | ---: | ---: |
| HIST1 | 1 | C291 de produto, cinco passos seriais | 3 441 → 3 685 | 23,450 |
| RECOMP1 | 1 | Grafo original recompilado, serial | 3 441 → 3 685 | 23,894 |
| OFF1 | 1 | Biblioteca candidata com reparações desligadas, serial | 3 441 → 3 685 | 23,952 |
| ON3 | 3 | Mesma biblioteca com reparações ativas, serial | 3 441 → 3 685 | 23,839 |
| B0 | 3 | Bloco, zero aceitações, duas continuações | 3 441 → 3 642 | 23,192 |
| B1 | 3 | Bloco, uma aceitação, duas continuações | 3 441 → 3 643 | 23,303 |
| B2 | 3 | Bloco, duas aceitações, duas continuações | 3 441 → 3 683 | 23,843 |

Os quatro ensaios seriais coincidiram em 19 ficheiros cada com a referência 173. Nos três blocos, o target confirmou respetivamente 190125, 50005 e 5671. As seis linhas de decisão, as seis distribuições das continuações e os nove estados de KV coincidiram com os controlos seriais independentes. A entrada de 189 posições é a fixture `log_medium`. O tempo inclui carga, prefill, sincronização, serializações e fecho; as profundidades finais diferem. A sessão nominal de dois pedidos conserva a sua medição anterior de 18,313 s até ao primeiro conteúdo final e 5,361 tok/s. [Medição do cliente HTTP](../../conversation/ordens.md)

## O custo dos experts à mesma profundidade confirmada

| Aceites de 2 | Cargas adicionais do candidato no corte, CPU / CUDA | Depois de mais dois tokens, CPU / CUDA | Peso lógico adicional no corte | Depois de mais dois tokens |
| ---: | ---: | ---: | ---: | ---: |
| 0 | +70 / +33 | +39 / +21 | +1 361 577 600 B | +793 152 000 B |
| 1 | +32 / +10 | +10 / +3 | +555 206 400 B | +171 849 600 B |
| 2 | −2 / 0 | −2 / 0 | −26 438 400 B | −26 438 400 B |

A previsão foi construída com os contadores de geração guardados no C269. Foi selada às 18:49:56 UTC, depois dos primeiros dois controlos seriais e antes de qualquer processo especulativo com o pack. O código C291 começa os contadores de geração em zero e incrementa uma vez por reserva. A conclusão válida publica o slot e cobra uma carga de 13 219 200 bytes de pesos. O verificador conferiu contadores monotónicos nos 1 440 slots, estado drenado nos cortes e igualdade das somas com as conclusões efetivas do pack à entrada e à saída de cada processo. Todas as previsões por dispositivo e profundidade coincidiram. São reservas reconciliadas com serviço concluído e bytes lógicos. O intervalo físico do NVMe, o tempo exposto ao pedido e a frequência natural das rejeições exigem os seus próprios relógios. [Cálculo com o C269](loads.py) · [Revisor dos dados do portátil](review.py)

MEDIDO no portátil com driver 620.73.04, 40 slots, quatro workers, ub32, contexto 8192 e o mesmo GGUF no NVMe interno. C55 admitiu 24 964 497 408 B. C118 antecedeu cada processo E20_R0. O máximo foi de 6 848 MiB na RTX e 15 990 972 416 B no cgroup, com zero swap. Cada braço registou 87–89 observações positivas do descritor do pack em O_DIRECT e só leitura. A energia estimada da placa ficou entre 274,8 e 291,7 J por processo. A energia do portátil é desconhecida. Foram zero pedidos HTTP. M3 PARTIAL e M4 NOT_MET. O ensaio de proposta real tem de cobrar a poluição após rejeição e a oportunidade de sobrepor os acessos, além da própria verificação.

O arquivo 176 contém 261 ficheiros e 466 331 457 bytes. O revisor reproduziu nos originais e no arquivo o mesmo SHA-256 `5c8923f2bd9a2b240433992219e4c2398c82aabddd43c1448a1d0cb9dbd0d30a`. [Manifesto 176](../../../../private_archive/part-176.json)

```sh
python3 -IB review.py --family "$FAMILY176" --family-sha256 6c3c96649a8226d97874569bb8012c925bc7781a85fa5bd65875709d1cc99e5e \
  --client "$CLIENT176" --window "$C55_176" --forecast "$FORECAST176" --history "$FAMILY173" \
  --target "$FAMILY169" --serial "$FAMILY165" --new-output-dir "$NEW"
```
