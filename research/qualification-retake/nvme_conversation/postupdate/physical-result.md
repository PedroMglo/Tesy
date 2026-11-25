# Resultado da conversa R0 após a atualização do driver

**MEDIDO — 2/2 pedidos naturais validados no portátil.** O mesmo servidor E20 respondeu ao primeiro pedido e usou a resposta efetiva como histórico no segundo. Neste turno incremental de 153 tokens, o primeiro conteúdo final chegou aos **20,385 s** e o decode foi de **4,767 tok/s** para 47 tokens. A conclusão validada chegou aos 20,656 s. Os alvos nominais continuam em 10 s e 6 tok/s. **M3 PARTIAL · M4 NOT_MET.** [Recibo compacto](physical-r01/evidence.json)

| Pedido | IDs oficiais de entrada | Cache / novos | Tokens de saída | Prefill / decode do servidor | Decode | Primeiro texto / primeiro final no cliente | Transporte / validação no cliente |
|---|---:|---:|---:|---:|---:|---:|---:|
| Código de cinco dígitos | 2 043 | 0 / 2 043 | 78 | 61,756 / 19,741 s | 3,951 tok/s | 62,475 / 81,075 s | 81,508 / 81,509 s |
| Repetir o código | 2 197 | 2 044 / 153 | 47 | 10,784 / 9,859 s | 4,767 tok/s | 11,461 / 20,385 s | 20,655 / 20,656 s |

As duas entradas coincidiram integralmente com os hashes oficiais C281. Houve dois streams completos com `[DONE]` e `finish_reason=stop`. O validador aceitou os cinco dígitos e a repetição exata. Os relógios de primeiro texto e primeiro final medem receção de fragmentos pelo cliente. O endpoint comunicou a contagem de saídas e deixou ausente a sequência completa de IDs gerados. O número de forwards e a energia física ficaram sem medição. [Contrato original](../protocol.md)

**Limite condicional deste pedido.** A 6 tok/s, os mesmos 47 tokens dispõem de 7,833 s de decode. Face aos 9,859 s medidos seriam necessários menos 2,025 s. Mesmo concedendo toda essa redução antes do primeiro conteúdo final, este chegaria aos 18,360 s. Restariam 8,360 s a retirar para alcançar o alvo de 10 s. Até eliminar todo o decode e manter as demais fases fixas deixaria 10,526 s. A conversa E20 anterior registou 21,443 s e 4,523 tok/s neste turno. As duas execuções correspondem a datas distintas e a auditoria do loader está ativa nesta identidade. A diferença é diagnóstica. [Par anterior](../README.md)

**Proveniência.** A checkout limpa estava em `14b409d75eaa0e6a976fd9b6ebb4b80396ee1df3`, árvore `a550401e1af77b0336ba79112ada222218b81d2f`. O pré-voo estático R01 e o C270 E20 deram PASS com a mesma origem de driver. O recibo privado C270 tem SHA `1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6`. O cliente verificou os mesmos 27 ELF no PID dono da porta no READY e após o segundo pedido; o diário do loader autenticou as 27 inicializações, incluindo libcuda, PTX JIT, NVVM e gpucomp do deployment 620.70.06. A busca opcional de libnvcuextend ficou sem fornecedor. A NVML do monitor foi selecionada no seu ambiente separado. [Protocolo físico](../../nvme_r0_gate/driver_pair/server_startup/physical-protocol.md)

**Recursos e encerramento.** A C118 recolheu 61 amostras em 60,134 s. Do Popen até READY decorreram 4,082 s; o processo durou 107,028 s e a unidade completa 168,974 s. O cgroup E20 atingiu 16 191 946 752 B, com zero swap e OOM. Máximos amostrados de 6 848 MiB na GPU, 83,5 °C na CPU, 57,78 °C na GPU e 49,85 °C no NVMe. O dono encerrou o servidor, que saiu com código zero, e confirmou o fecho da unidade e do listener.

O recibo físico privado tem SHA `cb191e31c2e3ee547a01228065a3c4253bdb312dd1e561d361f75365f065356a`. A compactação reaplica o verificador original ao par completo e verifica adicionalmente os mapas, o loader e o inventário. O comando seguinte reproduz o compacto na checkout e reserva uma saída exclusiva.

```sh
study=research/qualification-retake/nvme_conversation/postupdate
python3 -IB "$TESY_CHECKOUT/$study/compact.py" --repo "$TESY_CHECKOUT" \
  --raw-root "$TESY_PRIVATE_C281" --receipt-sha256 cb191e31c2e3ee547a01228065a3c4253bdb312dd1e561d361f75365f065356a \
  --new-output-dir "$NOVO_COMPACTO"
```
