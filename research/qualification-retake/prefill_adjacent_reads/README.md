# Juntar fatias contíguas deixa 1 015 gerações isoladas

**NO_GO como caminho isolado para primeiro conteúdo final em 10 s no C135 com decode a exatamente 6 tok/s.** Dos 1 222 jobs do prefill 5+148, apenas 207 poderiam ter outro ID fisicamente adjacente no mesmo tensor e no mesmo tile×layer, mesmo antecipando todas as waves desse layer. Conceder duração zero às leituras dos 207, aos kernels, às cópias e à coordenação deixa um piso de **6,276021 s** nas 1 015 gerações restantes. O próprio pedido dispunha de **2,427104 s** de prefill no cenário que antecipa até ao primeiro conteúdo todo o crédito do decode a 6. A diferença é 3,848916 s. O resultado anterior exigia duração fixa de todos os READ. Este continua a valer quando cada participante de um grupo contíguo recebe os seus bytes gratuitamente; fixa apenas as leituras isoladas. [Protocolo prospetivo](protocol.md) · [Recibo](replay-r2/receipt.json) · [Conta do orçamento C135](../prefill_read_floor/README.md)

| Chamada | Gerações | Participantes com fila testemunhada | Preads originais → plano | Candidatos no cenário mais generoso | Jobs isolados | Piso residual |
|---|---:|---:|---:|---:|---:|---:|
| 5 | 45 | 4 | 135 → 129 | 4 | 41 | 0,318946 s |
| 148 | 1 177 | 122 | 3 531 → 3 345 | 203 | 974 | 5,957075 s |

O plano testemunhado forma duas duplas na chamada de 5. Na de 148 forma 58 duplas e dois trios. Em cada grupo a última primeira emissão já ocorreu quando o primeiro worker retira uma das suas gerações. Os IDs são consecutivos no mesmo tensor; o grupo preserva tile, camada, wave do produtor e classe da primeira emissão. Nas 1 177 gerações da chamada de 148 houve 729 primeiras emissões por procura e 448 por preload, mais 356 enqueues de promoção do mesmo trabalho. O código confere a correspondência com o expert e slot da marca de origem. Os enqueues/dequeues observados sob o mutex demonstram a coexistência local de cada grupo; uma nova agenda de quatro workers teria de medir a contenção e o efeito dos grupos uns sobre os outros. [Verificador](screen.py) · [Origem do despacho e ordem gate/down/up](../prefill_io_order/make_plan.py)

O payload pedido nas duas chamadas conserva **16 153 862 400 B**. O plano reduz o número de preads em 192 e a soma dos comprimentos O_DIRECT pedidos de 16 168 660 992 para 16 167 874 560 B. A diferença de **786 432 B** corresponde às margens de alinhamento de 4 096 B duplicadas nas fronteiras. Os 126 experts participantes ainda precisariam de receber 1 665 619 200 B nas fatias e gerações de destino. O número de cópias adicionais depende dos buffers do candidato; a relaxação concede custo zero à entrega. O mecanismo difere de reempacotar três matrizes do mesmo expert em C293 e de as emitir em paralelo em C125b. A fixture de ordenação atual conservou o número de preads. [C293](../../C293-INTEGRATED-EXPERT-STORE-COST-NO-GO-20261006.md) · [C125b](../../C125B-COMPONENT-IO-RESULT-20260929.md) · [Ordenação no NVMe](../prefill_io_order/README.md)

**Limite.** O piso usa a maior cadeia de READ de um expert e a capacidade de quatro workers por tile×layer, com desconto de 1 µs por componente. O cenário generoso ignora inteiramente a distinção entre procura e preload e a ordem das waves para escolher participantes. Assim o veredito dispensa resolver as possíveis alterações na ordem de aceitação entre esses produtores. O relógio pertence ao C135; offsets e comprimentos são lógicos e alinhados para a API de leitura. Alterações no serviço dos 1 015 isolados por outra política de residência, mecanismo de armazenamento ou contenção exigem nova medição. O efeito marginal real em NVMe e os critérios do turno natural E20 permanecem desconhecidos.

### Reprodução

```sh
LC_ALL=C python3 -B research/qualification-retake/prefill_adjacent_reads/screen.py \
  --pr45-checkout "$TESY_PR45_CHECKOUT" --trace "$TESY_C135_TRACE" \
  --inventory "$TESY_C7_GGUF_INVENTORY" --new-output-dir "$DESTINO_NOVO"
python3 -B research/qualification-retake/prefill_adjacent_reads/test_screen.py
```

O inventário é o JSONL histórico de 687 tensores. O verificador confirma o digest, o formato e os offsets dos 108 tensores MXFP4, a identidade do journal e a reconstrução do piso anterior. As duas execuções emitiram o SHA-256 `5f4c587149b268dd42964dd60b99a4f021131df9c875625537861b144b955de9`. A segunda durou 0,39 s e usou 76 896 KiB de RSS máximo. Os dois testes sem modelo e o Ruff passaram; o primeiro lint detetou três linhas compridas corrigidas antes da segunda execução. Zero pesos, GPU ou Actions.
