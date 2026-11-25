# Que parte da conversa cobrem as quatro waves de serviço?

**GO apenas para desenhar a medição.** A call de 148 contém 1 296 regiões de remap. Em 1 022 não há procura, em 36 todos os consumidores acertam no primário em ambas as políticas, e em 238 pelo menos uma delas entrega pesos de RAM ou disco. As duas waves de prefill da fixture anterior pertencem às 32 em que a política nova retira leituras de disco. Os tempos medidos nessas quatro waves não identificam o ganho integral da conversa. [Pré-registo do censo](protocol.md) · [Medição das quatro waves](../t1_primary_layout/README.md)

No mesmo processo do segundo pedido, a seleção prospetiva por hash produziu 42 estratos representados, incluindo serviços iguais entre os braços. Os pesos comuns a esses sites incluem 310 experts e 930 componentes indexadas. A medição anterior abrangia quatro sites com 29 experts. A tabela dá o censo, as ocorrências cobertas pela nova amostra e as leituras de disco **lógicas** do censo completo. [Recibo por estrato, origem e layout](evidence/receipt.json)

| Fase | Waves no PFJ | Consumidores | Waves selecionadas | Consumidores selecionados | Leituras do disco LRU / expulsão prioritária |
|---|---:|---:|---:|---:|---:|
| Call de 5 | 35 | 459 | 6 | 66 | 34 / 34 |
| Call de 148 | 1 296 | 3 367 | 19 | 198 | 1 015 / 978 |
| Decode antes do primeiro final | 1 584 | 6 336 | 16 | 64 | 1 124 / 955 |
| Fronteira de ±1 ms | 1 | 4 | 1 | 4 | 0 / 0 |
| Decode posterior | 71 | 284 | 0 | 0 | 19 / 19 |

Na call de 148, o vetor ordenado de origem dos pesos é idêntico em 1 211 waves. Entre as restantes, 53 mantêm o número de faltas de disco e alteram a distribuição de origens; 32 reduzem as faltas. No decode inequivocamente anterior ao primeiro final, contam-se 1 274 idênticas, 159 com a mesma cardinalidade e caminhos diferentes, 149 com menos e duas com mais leituras de disco. A região na fronteira tem quatro hits primários na LRU, contra três hits primários e uma entrega de RAM na política nova. A janela de ±1 ms evita decidir a inclusão desta região a partir da precisão dos relógios. O marcador do cliente pertence ao mesmo T2; um backend alterado poderá mudar a sua posição.

O censo usa as mesmas regras de leitura de disco e de reposição dos residentes, e o mesmo banco causal selado de 353 entradas que a simulação original. Antes de iniciar decode, a restituição requer mais 185 leituras de disco e quatro entregas de RAM com LRU, ou 172 e 88 com a prioridade às vítimas recuperáveis. São custos adicionais à tabela. A sua ordem de serviço e o seu custo temporal ficam em aberto. [Estado à entrada do decode e controlo causal](../t1_primary_victim/README.md)

**Custo para uma próxima medição.** As 42 waves selecionadas exigiriam 84 leituras de disco e nove entregas de RAM com LRU, ou 78 e 23 com a nova política. A maior wave exige 14 entregas. Preparar os 310 registos necessitaria de uma fatia compacta de 4 098 785 280 B. As quatro células de política × layout, com uma passagem de controlo e quatro blocos, pediriam **21 426 974 720 B de FD por processo**, acima do orçamento de 8 GB do ensaio anterior. A admissão física requer um desenho e orçamento próprios. O plano conserva as multiplicidades e permite definir o estimador antes de medir. O presente censo não atribui duração às waves, às cópias RAM→GPU, ao grafo ou à conversa.

## Reprodução

Protocolo em `26d0243d`, implementação em `d2cbd729`. O plano usa o PFJ e o selo de T1 da parte 40, o recibo causal da parte 45 e o plano privado autenticado da parte 44. Os digests do índice e readback C290 são conferidos contra o inventário GGUF C7; o ficheiro de pesos é consultado apenas por stat. Os dois processos confirmaram byte a byte o plano privado, SHA-256 `63c5bffd8e8b00f7dd7d390326250d62c5d31dd2249c5e735256f9fa1ee0630b`, e o recibo, SHA-256 `867fd2336e37fc0c965b11f178fe797bf403fb019ea6db7130cdc962c8fda02c`. Custo real de 0,66 / 0,67 s e 80 340 / 79 976 KiB de RSS. Zero forwards e leituras de pesos.

```sh
cd research/qualification-retake/phase_fd/integrated/t1_full_workload
python3 -IB test_plan.py
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  timeout 120s prlimit --as=536870912 --cpu=120 --fsize=4194304 -- python3 -IB plan.py \
    --part "$PART40" --model "$GGUF_NVME" --inventory "$C7_INVENTORY" \
    --prepared-dir "$T1_SEAL" --causal-dir "$CAUSAL_RECEIPT_DIR" \
    --old-plan "$FOUR_WAVE_PLAN" --index "$C290_INDEX" --readback "$C290_READBACK" \
    --new-output-dir "$NOVO"
```
