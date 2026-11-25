# Volume de leitura durante o prefill e o decode da conversa R0

**NO_GO_SERVICE_FIXED** no turno nominal se todos os bytes do piso de prefill tiverem de ser servidos dentro dessa fase a 4,5 GB/s e o decode chegar exatamente a 6 tok/s. O piso observado é **12,945 GB**; o orçamento condicional de **2,424377 s** comporta **10,910 GB**. Mesmo concedendo todo o ganho de decode antes do primeiro conteúdo final, seriam precisos pelo menos **5,339 GB/s**, ou servir pelo menos **2,035 GB** por outra via, deixar de os pedir, ou antecipá-los com custo contabilizado. M4 continua NOT_MET. A taxa de 4,5 GB/s é uma hipótese de cenário; a execução mediu contadores do processo. [Protocolo congelado](protocol.md) · [Recibo dos dois turnos](evidence-r01/evidence.json)

| Intervalo original | T1, 2 043 novos, 78 saídas | T2, 2 044 em cache + 153 novos, 47 saídas |
| --- | ---: | ---: |
| Prefill nativo | ≥42,435 GB | 12,945–17,898 GB |
| Decode nativo | 28,567–34,084 GB | ≥12,843 GB |
| Pedido até primeiro conteúdo final | ≥73,103 GB | 28,778–32,933 GB |
| Pedido até conclusão do transporte | ≥74,091 GB | ≥29,766 GB |
| Pedido até validação | ≥74,091 GB | ≥29,766 GB |

GB são decimais. Os pisos de decode são 366,2 MB e 273,3 MB por token no denominador do servidor, respetivamente. O primeiro ID de saída é amostrado no fim do prefill; o T2 executa 46 avaliações subsequentes. O kernel fornece read_bytes para atividade de leitura na camada de blocos atribuída ao processo. O contador inclui outros ficheiros abertos. Pedidos de leitura, bytes codificados de experts, transferências PCIe e bytes físicos da NAND têm autoridades diferentes. No prefill T2, rchar ficou entre 12 949 299 200 e 17 897 627 648 B e syscr entre 2 936 e 4 058. O GGUF do NVMe teve um ou dois descritores O_DIRECT em 157 amostras; na primeira ainda estava fechado. A identidade do PID, start_ticks, cgroup e manifesto completo coincide nas 158 observações. [Contabilidade do kernel](https://docs.kernel.org/filesystems/proc.html#proc-pid-io-display-the-io-accounting-fields)

O crivo autentica os 31 ficheiros privados, o compacto físico, quatro ficheiros de source e o terminal C281. No C269 Linux, ggml_time_us usa CLOCK_MONOTONIC. Em server-context.cpp, a primeira amostra encerra o prompt e inicia o decode; o último relógio de decode antecede a resposta final. Os relógios deixam 11,303 ms no T1 e 11,991 ms no T2 entre a soma das durações nativas e a duração de transporte. O monitor arredonda elapsed_s a 1 ms; o contador é lido dentro da recolha anterior à marca arredondada. O zero do monitor pode deslocar-se 4,082 s entre a marca de lançamento e READY. Para cada intervalo foi usado um só deslocamento comum a todas as amostras; verificaram-se os extremos, as igualdades e uma posição entre cada par de cortes sucessivos. Os pisos e tetos de fases distintas podem ocorrer com deslocamentos diferentes. O sinal ≥ indica uma extremidade exterior sem duas amostras que a cerquem para todo o intervalo. [Implementação e fontes autenticadas](screen.py) · [Sessão de origem](../postupdate/physical-result.md)

A atribuição a experts e ao caminho crítico continua por medir. Em unidades do payload lógico de 13 219 200 B, 2,035 GB correspondem a pelo menos 154 cargas completas se cada carga evitasse igual volume de serviço. A política causal de frequência retirou 121 cargas do incremento nominal C294 e acrescentou 527 no decode da mesma sequência. [Reposição e custo no decode](../../prefill_causal_continue/README.md)

Uma intervenção que só acelere cálculo ou cópia precisa também de demonstrar que a parcela obrigatória no mesmo tier cabe no orçamento. Para distinguir redução de recargas de simples deslocação temporal, a próxima observação precisaria dos bytes e das barreiras por geração/descritor e do estado de residência que chega ao primeiro decode. O estudo reutilizou a sessão existente. A reprodução lê apenas o arquivo e o source, sem pesos nem GPU.

```sh
python3 -B research/qualification-retake/nvme_conversation/phase_reads/screen.py \
    --raw-root "$TESY_C281_E20" --backend "$TESY_C269_SOURCE" \
    --new-output-dir "$NOVO_DIRETORIO"
python3 -B -m unittest discover -s research/qualification-retake/nvme_conversation/phase_reads
```
