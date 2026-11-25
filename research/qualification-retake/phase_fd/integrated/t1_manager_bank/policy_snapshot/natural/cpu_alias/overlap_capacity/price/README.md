# Margem que as 18 leituras evitadas deixam no pedido

**TRACE_DERIVED.** Os 14 hits adicionais de prefill e quatro de decode
deixam **77,968 a 85,273 ms por pedido** para pagar a manutenção adicional
do banco, a entrega a partir das páginas, os remapeamentos e o último leitor,
se os trabalhos do NVMe conservarem as durações observadas. Para que haja
aceleração nas quatro combinações, o custo líquido adicional teria de ser
inferior a **77,968 ms** (77 968 070 ns antes de arredondar). A partilha
também pode reduzir cópias durante T1. O custo dessas cópias no pedido
integrado precisa de uma ablação independente.

| Ordem prefill / decode | Défice com G=0 s | Ganho de prefill simulado ms | Ganho de decode ms | Orçamento de novos custos ms | Teto com todo o worker-tempo ms | Défice mesmo no teto s |
|---|---:|---:|---:|---:|---:|---:|
| RP / RP | 2,412 | 69,179 | 15,617 | 84,796 | 291,092 | 2,120 |
| RP / PR | 2,444 | 69,179 | 16,094 | 85,273 | 291,570 | 2,152 |
| PR / RP | 2,187 | 62,351 | 15,617 | 77,968 | 265,009 | 1,922 |
| PR / PR | 2,220 | 62,351 | 16,094 | 78,445 | 265,487 | 1,954 |

**NO_GO para suficiência isolada aos preços fixados.** Mesmo creditando
todo o serviço de worker retirado no prefill, a combinação elimina cerca de
12% do défice. O benefício de páginas na fase de captura continua elegível
para uma fixture COPY/ALIAS com o mesmo histórico de T1 e as mesmas rotas.
O intervalo da tabela é entre ordens. O tempo real com 14 pedidos de
leitura a menos e a duração dos restantes READs dependem da contenção e
da fila efetiva. [Margem do pedido](../../../prefill_frontier/transport/joint/README.md)

| Ordem / call | Parede medida ms | Worker-tempo retirado ms | FIFO inicial ms | FIFO com os hits ms | Diferença ms |
|---|---:|---:|---:|---:|---:|
| RP / 5 | 207,774 | 22,993 | 206,799 | 201,368 | 5,430 |
| RP / 148 | 5 337,512 | 252,482 | 5 333,642 | 5 269,894 | 63,748 |
| PR / 5 | 174,156 | 14,569 | 173,902 | 170,019 | 3,883 |
| PR / 148 | 5 146,889 | 234,823 | 5 144,177 | 5 085,709 | 58,468 |

A fila simulada mantém quatro workers, os preços individuais e a barreira
entre as duas chamadas. Nos timestamps observados, cada READ retirado
sobrepunha-se inteiramente a pelo menos outro READ mantido. A parcela
exclusiva da união é zero nas quatro travessias. Na simulação, a remoção
permite adiantar pedidos posteriores. Cada remoção deixa até a sua duração
original de folga num dos quatro workers: ordenar os quatro tempos de
disponibilidade preserva a sua ordem componente a componente e, em cada
passo FIFO posterior, não amplifica a diferença máxima. Daí o teto pela soma
das durações retiradas quando os preços individuais são constantes.

No decode conservam-se os SET com homólogo no mesmo sítio e o máximo das
cadeias por callback. Na call 80, por exemplo, o job poupado demorara
12,667/12,832 ms em READ, mas outro job limita o ganho a 1,431/1,487 ms.
Os quatro jobs evitam 52 876 800 B de payload de disco. Os 14 de prefill
evitam 185 068 800 B. Os mesmos 237 945 600 B continuam a ser necessários
aos consumidores. O recibo detalha as quatro gerações de decode, a união
de parede e o worker-tempo do prefill. [Recibo](receipt.json)

O método foi pré-registado em `c3d2aac7`, e o programa e as contraprovas
congelados em `db2a1d01`. Dois processos sem pesos e sem GPU recertificaram
as identidades T1, os READs e o preço-base. Fecharam em 1,15/1,16 s e
93 388/93 068 KiB de RSS. Ambos produziram SHA-256
`b9ffde2d895be6691ab150a8763ed9dd160ddda3a2327efd8fa343c4cc5db159`.

```sh
python3 -IB "$STUDY/test_screen.py"
timeout 120 prlimit --as=805306368 --cpu=118:120 --fsize=8388608 -- \
  python3 -IB "$STUDY/screen.py" --family "$ON_OFF_R02" --prefill "$PREFILL_PLAN" \
  --decode "$DECODE_PLAN" --pre-rp "$PREFILL_RP" --pre-pr "$PREFILL_PR" \
  --dec-rp "$DECODE_RP" --dec-pr "$DECODE_PR" --new-output-dir "$NOVO"
```
