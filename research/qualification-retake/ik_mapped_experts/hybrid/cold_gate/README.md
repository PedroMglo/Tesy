# O custo de passar os pesos frios por RAM antes da RTX

**NO_GO para copiar do mmap para um scratch CPU antes do H2D, neste corte.** O caminho com scratch demorou mais 26,293 e 8,470 ms nas ordens inversas, embora tenha poupado 8 601 600 B de leituras do cgroup em cada par. Os quatro braços partiram da matriz fria e entregaram os mesmos 215 913 600 B nos mesmos slots. A referência independente e as duas guardas passaram nos quatro casos. [Protocolo em `e6156aec`](protocol.md) · [Resultado em ns e bytes](result.json)

| Ordem | Percurso | Serviço até à última barreira, ms | Preparar origem, ms | Submeter H2D, ms | Drain, ms | NVMe do cgroup, MB | Namespace até à barreira, MB |
|---|---|---:|---:|---:|---:|---:|---:|
| Direto primeiro | Direto | 196,183 | 0,031 | 195,964 | 0,065 | 518,525 | 508,154 |
| Direto primeiro | Scratch | 222,477 | 205,834 | 16,471 | 0,085 | 509,923 | 509,923 |
| Scratch primeiro | Scratch | 210,108 | 193,440 | 16,463 | 0,085 | 509,923 | 509,923 |
| Scratch primeiro | Direto | 201,638 | 0,021 | 201,474 | 0,035 | 518,525 | 508,285 |

MEDIDO na RTX 4060 Laptop e no GGUF original do NVMe interno. O custo de aquisição deslocou-se da chamada CUDA para o memcpy da CPU. O tempo total inclui a submissão, a sincronização e o laço. A verificação D2H posterior demorou 106–119 ms por braço. O PID e o cgroup coincidiram ao nível dos bytes de leitura. O contador global do namespace, observado na conclusão da stream, tem uma fronteira distinta. O ensaio não mede o fim de todo o readahead do controlador.

Na camada 0, a matriz tem 137 701 páginas de 4 KiB. Em cada braço, `mincore` encontrou zero residentes antes e 124 493–126 534 depois. Os mesmos 33 intervalos de gate cobriram 49 experts. No direto, as leituras cobradas foram 2,402 vezes o payload nos dois braços. A taxa global de serviço útil foi 1,071–1,101 GB/s. Este resultado torna testável uma mudança no modo de ler os intervalos. Os tempos de uma matriz fria não identificam os segundos recuperáveis na conversa.

**Objetivo de produto.** A melhor observação nominal da conversa com pack continua em 18,313 s até ao primeiro conteúdo final e 5,361 tok/s, com 18,565 s até à validação. As duas observações do pack chegaram mais cedo do que os controlos com o mesmo NVMe. Os quatro cortes desta unidade fizeram zero forwards e zero pedidos de produto. M3 PARTIAL, M4 NOT_MET. [Resultados dos dois turnos](../../../packed_nvme_manifest/server_profile/conversation/ordens.md)

## Procedência e reprodução

O commit físico foi `7f2505d3dd07cc28342ab24d3ba0d99a19419e66`, com árvore limpa, kernel 7.3.4-200.fc44.x86_64 e driver 620.73.04. A fonte foi a agenda OFF288 C110 do lote 144 e o plano de tensores do lote 138. Os dois C118 recolheram 61 amostras em 60,138 e 60,144 s. Os filhos duraram 1,692 e 1,701 s, atingiram 308 MiB de VRAM e saíram com código zero. O pico do scope foi 842 948 608 B, swap zero. Depois do fecho a RTX ficou em 2 MiB e o scope inativo. Energia integrada DESCONHECIDA. O lote 145 contém 22 ficheiros e 223 612 B. Os dois revisores sobre originais e arquivo devolveram o mesmo JSON. [Manifesto](../../../private_archive/part-145.json)

```sh
d=research/qualification-retake/ik_mapped_experts/hybrid/cold_gate
family="$ARCHIVE/part-145/tesy-ik-cold-gate-service-20261126-r01"
reference="$ARCHIVE/part-145/tesy-ik-cold-gate-reference-20261126-r01/receipt.json"
python3 -IB "$d/grade.py" --family "$family" --reference "$reference" \
  --family-sha256 232be642acd7b72e7ef50f86753410b33ac36d44304120e8548e59748aa60f97 \
  --new-output-dir "$NEW"
python3 -IB research/qualification-retake/private_archive/verify.py \
  "$ARCHIVE" research/qualification-retake/private_archive/part-145.json
```
