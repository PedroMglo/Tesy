# A janela disponível para servir os pesos no prefill de T2

**NO_GO condicionado a manter o volume no mesmo dispositivo e na mesma janela, a 4,5 GB/s.** No controlo OFF, o prefill de 153 tokens tem pelo menos **14 306 082 816 B** de leituras atribuídas ao processo. Com o filtro de contexto e as cinco verificações sem preço tratadas como gratuitas, caberiam 13 945 874 837 a 14 082 436 337 B. O saldo exige retirar da janela pelo menos **224–360 MB decimais**, antes de cobrar aqueles blocos e o trabalho de computação exposto. Com a seleção perfeita apenas entre os despachos já medidos, a insuficiência é **7,587 GB**. A decisão diz respeito ao modelo de serviço fixo. A receita operacional continua com 40 slots, M3 PARTIAL e M4 NOT_MET. [Pré-registo](io-protocol.md) · [Resultados compactos](io-result.json) · [Custos do filtro](context.md)

| Braço | Relógio até READY (s) | Incerteza máxima do zero após cleanup (s) | Prefill T2, mínimo–máximo de read_bytes (GB) | Leituras até ao primeiro final, mínimo (GB) | Redução mínima de prefill se o decode chegar exatamente a 6 tok/s (GB) |
|---|---:|---:|---:|---:|---:|
| ON | 4,064 | 0,045 | 16,144–18,550 | 31,984 | 5,158 |
| OFF | 4,097 | 0,355 | 14,306–18,392 | 29,591 | 3,446 |
| P | 4,084 | 0,121 | 14,888–18,259 | 29,300 | 4,046 |
| R | 4,107 | 0,147 | 15,825–17,876 | 29,850 | 4,812 |

O monitor guardou a sua duração arredondada a 1 ms. A paragem confirmada pelo controlador ocorreu depois de este ler o manifesto terminal. Logo, o zero desse monitor ocorre até ao instante de cleanup menos a duração mínima compatível com o arredondamento. A interseção com os limites de lançamento e READY conservou ou estreitou todos os intervalos. Só com READY, o piso de prefill de OFF era 13,185 GB e o intervalo abrangia ambos os volumes admitidos pelo filtro. Com a observação de cleanup já guardada, o piso excede ambos. Cada cálculo usa um deslocamento comum para todas as amostras de um processo. A última coluna dá à latência do primeiro final todo o crédito necessário para o decode chegar a 6 tok/s e conserva o exterior.

No filtro as cinco verificações novas antecedem o primeiro delta final. Se introduzirem em conjunto mais um segundo exposto nessa janela, entram mais 4,5 GB na redução exigida enquanto existir tempo de prefill disponível. Esta conversão pressupõe que o volume contabilizado tem de ser transportado dentro da fase pelo mesmo NVMe à taxa indicada. Completude física de I/O, bytes pedidos por expert, sobreposição entre trabalho e leitura e tráfego PCIe são observações distintas. O kernel contabiliza `read_bytes` ao processo em armazenamento de blocos. O ficheiro compacto guarda também `rchar`, `syscr`, os intervalos de T1 e T2, o transporte, a validação e os limites superiores que ficou impossível identificar por falta de uma amostra posterior. [Contadores do kernel Linux](https://docs.kernel.org/filesystems/proc.html#proc-pid-io-display-the-io-accounting-fields)

A análise histórica de C281 foi reproduzida byte a byte e os três testes de extremos passaram. A medição física de origem tem SHA-256 `8e52a3e200fa03d005f4b25a036a3860ece0f359d42f38d0166e900fa6d655ae`. O auditor aplicado aos quatro braços foi fixado em `e1f4bc9a60cfa9d0ebcdcd5fd2d845051be663fb`. As reaberturas dos originais e do arquivo privado produziram `b29198b294b35206293895a01f734428fa49ddd32a2ec5e235e0d0b4ba9b4183` em 0,53 s cada, com picos de cgroup de 39,5 e 40,4 MiB, zero swap e zero forwards novos. A parte 187 guarda os dois resultados e os logs, 64 922 B em quatro ficheiros. [Código](prefill_io.py) · [Manifesto](../../../../../../../../../../../private_archive/part-187.json)

```sh
python3 -IB "$HTTP/prefill_io.py" --family "$AR/part-185/tesy-c281-cpu-rows-http-20261126-r02" \
  --review "$FOUR_ARM_REVIEW" --context "$CONTEXT_FILTER_REVIEW" \
  --commit "$MEASUREMENT_COMMIT" --new-output-dir "$NEW_IO_REVIEW"
```

Para distinguir recargas evitáveis de primeiros acessos obrigatórios, a observação seguinte é a identidade camada/expert e a geração de cada reserva nas cinco tiles da mesma chamada de 148. A contagem estabelece se eliminar todas as recargas observadas daria sequer o volume necessário antes de alterar o scheduler.
