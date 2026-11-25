# Três leituras simultâneas para uma única falta

**NO_GO no estrato C125B.** Nos 638 grupos do decode histórico de C123 com uma admissão, submeter as três componentes em paralelo poupou 0,20% e 2,75% do tempo dos grupos. Ambos os pares melhoraram. A mediana dos ganhos foi 1,48%, abaixo dos 15% que justificariam testar um manager de quatro workers no NVMe atual. O ensaio original usou O_DIRECT e os mesmos offsets do GGUF nos quatro braços. [Protocolo](protocol.md) · [Recibo reproduzido](evidence/receipt.json)

| Par | T0 serial (s) | T1 paralelo (s) | T0 médio (ms/grupo) | T1 médio (ms/grupo) | Poupança média (ms/grupo) | T1/T0 | Grupos mais rápidos |
|---|---:|---:|---:|---:|---:|---:|---:|
| A1/B2 | 4,401123 | 4,392285 | 6,8983 | 6,8845 | 0,0139 | 0,997992 | 358/638 |
| A4/B3 | 4,543593 | 4,418504 | 7,1216 | 6,9256 | 0,1961 | 0,972469 | 427/638 |

Os 638 grupos pediram 8 433 849 600 bytes lógicos por braço. O relógio do grupo começa antes da submissão e termina depois da recolha de todas as leituras. Cada ganho usa a razão entre as somas de tempo dos mesmos grupos. Não houve empates entre durações emparelhadas neste estrato.

| Admissões por grupo | Grupos | Admissões | Ganho A1/B2 | Ganho A4/B3 | Mediana dos ganhos |
|---|---:|---:|---:|---:|---:|
| 1 | 638 | 638 | +0,20% | +2,75% | +1,48% |
| 2 | 271 | 542 | −5,93% | −4,31% | −5,12% |
| 3 | 83 | 249 | −2,41% | −4,53% | −3,47% |
| 4 | 20 | 80 | +5,27% | −1,82% | +1,72% |
| Todos, soma de grupos | 1 012 | 1 509 | −2,04% | −1,07% | −1,55% |

No relógio integral dos braços em ordem ABBA, C125B mediu 10,180830 / 10,420241 / 10,443460 / 10,317326 s. Entre 0,147 e 0,182 s por braço estiveram fora dos relógios dos grupos. Os ganhos integrais foram −2,35% e −1,22%, mediana −1,79%, com 19 947 772 800 bytes lógicos por braço e zero erros de leitura ou paragens por recursos. [Decisão física C125B](../../../results/c125b-component-io-probe-20260929T1555Z/decision.json)

O controlo tinha um pool de quatro workers e submeteu uma tarefa serial por expert. O candidato tinha doze workers e submeteu uma tarefa por componente. Nos grupos de uma admissão, isto permite até uma e três leituras em curso, respetivamente. A história dos grupos anteriores, as filas do dispositivo e o custo de submissão Python fazem parte da medição. Nenhum destes registros mede a concorrência efetiva dentro do NVMe. Um manager nativo teria ainda de manter o claim e publicar a geração depois das três leituras. A decisão cobre o armazenamento na sequência C123 fornecida. Prefill, tok/s de decode e primeiro conteúdo de uma conversa continuam a precisar dos seus relógios próprios. Só uma premissa quantitativa nova sobre serviço/submissão no dispositivo atual justifica reabrir a fixture. [Implementação de C125B](../../../tools/c125_component_io_probe.py)

**Reprodução sem modelo.** A medição original foi feita em `27e46fa5c5e01be6b154ff3de4a4792942fc5e5c`. A reanálise congelou o protocolo em `094c719772aeb806f8e2e7a9f9cdee859c7a1047` e o código em `258753c848b6425d9dd90a64a8739968797f12b4`. As confirmações R01 e R02 demoraram 0,46 s cada e usaram 90 824 e 90 908 KiB de RSS. Emitiram recibos idênticos com SHA-256 `237e45eba7c05d8df315629ff416cdeef3610650fb5b2ef05f7113091859361b`. A reanálise leu os quatro vetores históricos, o trace C123 e o inventário de offsets. Usou zero leituras de pesos e zero GPU.

```sh
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B research/qualification-retake/c125_singleton/screen.py \
  --repo "$PWD" --historical-results "$TESY_C7_RESULTS" --new-output-dir "$NOVA_SAIDA"
```
