# Limite da promoção estática de coortes completas

**NO_GO para chegar a seis passos fornecidos/s neste regime.** Mesmo escolhendo com conhecimento do futuro os 64 experts adicionais que se instalam gratuitamente na GPU, os quatro C294 deixam pelo menos 8,103–9,535 s nos 32 passos. A meta exige até 5,333 s. Cada passo mantém o grafo R0 e os quatro experts oficiais de cada camada. Só se antecipa uma camada CPU quando os quatro pesos estão presentes na GPU. O limite concede tempo zero a toda a janela dessa camada, incluindo atenção, router, esperas e compute. [Protocolo anterior à contagem](protocol.md) · [Recibo R3](evidence-r3/receipt.json)

| C294 trace-ON | Decode nativo (s) | Redução necessária (s) | Teto de poupança (s) | Piso restante (s) | Teto passos/s | Mínimo de experts para o teto tocar seis |
|---|---:|---:|---:|---:|---:|---:|
| nominal153 #2 | 9,381 | 4,048 | 1,279 | 8,103 | 3,949 | 353 |
| nominal153 #3 | 9,415 | 4,082 | 1,278 | 8,137 | 3,933 | 356 |
| code153 #2 | 10,986 | 5,653 | 1,485 | 9,501 | 3,368 | 537 |
| code153 #3 | 11,010 | 5,676 | 1,475 | 9,535 | 3,356 | 539 |

**MEDIDO · capacidade de referência.** Na RTX 4060 Laptop com 8188 MiB, o C55 R5 parava a 7676 MiB totais. A família WRT40 atingiu 6868 MiB nos quatro braços E20. Foi possível colocar 9, 9, 12 e 11 amostras completas de VRAM dentro do decode, usando as durações do próprio braço, antes de consultar os valores das amostras. Todas registaram 6868 MiB. No supervisor o relógio começa antes do Popen e termina após o processo. O decode só pode começar depois do prefixo e incremento, e tem de terminar antes do fecho do processo. A interseção de todos os intervalos de decode possíveis permite identificar estas amostras sem assumir que o máximo de prefill coincide com o de decode. A margem de 808 MiB corresponde a 847 249 408 B. Cada chave (camada, expert) necessita pelo menos três matrizes de 4 406 400 B, logo 64 chaves deixam 1 220 608 B. Mesmo oferecendo 1 MiB suplementar para arredondamento continuam a caber só 64. A reserva de pesos é adicional aos pools, KV e workspace observados. O cap C55 de RAM foi 22,5 GiB e o cgroup E20 usou high=max 20 GiB. [C55 R5](../nvme_admission/evidence-20261125-r5/window.json) · [Braços da família WRT40](../warm_route_family/evidence-r1.json) · [Relógio do monitor](../../../tools/run_bounded.py)

**FORMAL, condicionado à agenda.** Há 800 coortes CPU por braço, com 1134 identidades distintas no nominal e 1245 no código. O verificador confirmou a ordem e os ranks de todas as 1152 rotas de decode e selecionou os intervalos disjuntos das 25 camadas CPU. Somou cada duração nas quatro chaves requeridas e dividiu por quatro a soma das 64 pontuações maiores. Uma coorte realmente completa oferece exatamente a sua duração a essa soma; uma coorte incompleta pode ainda oferecer crédito parcial, o que favorece o teto. Com peso unitário, até o número de coortes completas fica limitado a 176/800 no nominal e 170/800 no código. Os máximos por tempo e por contagem podem corresponder a escolhas distintas. O certificado passou contra enumeração exata de uma fixture pequena; uma coorte com um ID repetido foi rejeitada. [Verificador](bound.py) · [Âncora de ranks](../warm_route_reference/protocol.md)

O cálculo temporal usa só o relógio do respetivo C294 e o seu próprio decode. O piso do intervalo interno do journal diverge do valor nativo por menos de 3 µs nos quatro braços. A transformação preserva a duração das partes exteriores às coortes promovidas. O tempo de outros workers e os totais de prefixo, incremento e drenagem não geram crédito. Os limites necessários de 353–539 experts equivalem a 4,35–6,64 GiB só nas três matrizes adicionais; são fronteiras da relaxação. Não se demonstrou um conjunto simultaneamente realizável com essas capacidades. Uma alteração que liberte memória R0, divida experts do mesmo top-4 entre dispositivos ou modifique o serviço de camadas sem o top-4 residente abre uma hipótese diferente. O protocolo natural de M3/M4 continua a exigir tokens confirmados e relógio do cliente. [Âmbito dos relógios nativos](../../../tools/expert_service_window.cpp)

### Reprodução

Usar o raw C294, a raiz privada da família WRT40 com o seu resource-policy.json R5 e raw/ de monitores, e um diretório de saída novo. O verificador confirma manifestos, hashes dos dois braços de cada caso e seleção de IDs antes do cálculo. A reprodução R3 levou 0,129 s e 30 816 KiB de RSS, sem modelo ou GPU. R1 falhou pelo espaço virtual inicial do Python e R2 reportou uma marca de RSS herdada do launcher. R3 conservou o script e reproduziu todos os campos científicos de R2 com um filho novo. [Ambiente e tentativas preservadas](environment.md)

```sh
env -i PATH=/usr/bin:/bin LC_ALL=C /usr/bin/python3 -I -S -B - \
  "$TESY_C294_RAW" "$TESY_WRT40_FAMILY" "$NEW_OUTPUT_DIR" <<'PY'
import subprocess
import sys
subprocess.run([sys.executable, "-I", "-S", "-B",
                "research/qualification-retake/gpu_cohorts/bound.py",
                "--raw-dir", sys.argv[1], "--wrt-family-dir", sys.argv[2],
                "--new-output-dir", sys.argv[3]], check=True)
PY
```
