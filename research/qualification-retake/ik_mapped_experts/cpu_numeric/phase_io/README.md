# Leitura do NVMe durante as duas chamadas do canário ik

**REPRODUZIDO.** Durante a segunda chamada, que forneceu o token teacher 976,
o contador de bytes lidos do cgroup no 259:0 cresceu **pelo menos
3 169 058 816 B mais em D0 do que em D1**. Durante o prefill de 16 tokens a
diferença mínima foi de 1 538 220 032 B. Há uma observação de cada modo, D0
primeiro. A ordem, o estado inicial da cache e as leituras iniciadas numa fase
e contabilizadas noutra impedem atribuir estes deltas à política de prefetch.
[Recibo por fase](result.json) · [Protocolo da reanálise](protocol.md)

| Contador e chamada | D0, intervalo em GB | D1, intervalo em GB | D0 menos D1, intervalo em GB |
|---|---:|---:|---:|
| Cgroup 259:0, prefill | 38,162–40,586 | 33,829–36,624 | +1,538–6,756 |
| Cgroup 259:0, teacher | 5,346–7,991 | 0–2,177 | +3,169–7,991 |
| Namespace nvme0n1, prefill | 38,202–40,611 | 33,943–36,741 | +1,461–6,668 |
| Namespace nvme0n1, teacher | 5,346–8,000 | 0–2,196 | +3,150–8,000 |

GB corresponde a 10⁹ bytes. O namespace inclui todos os processos e usa
setores de 512 B. O 8:0 reporta 458 752 B em toda a janela de D1. D0 não
reportou esse dispositivo. O limite inferior de zero no teacher D1 também
admite leituras positivas. Os limites por fase são marginais; os seus máximos
podem resultar de alinhamentos diferentes. Para load, contexto e cleanup o
intervalo da diferença contém zero nos dois contadores principais.

## Como delimitar as fases

O supervisor mede 41,655796622 s e 28,107402092 s até observar a saída. Entre
a primeira e a última marca nativa passaram 41,439386590 s e 27,910915888 s.
A marca de início do loader pode situar-se de 0 a 216,410032 ms em D0 e
de 0 a 196,486204 ms em D1, relativamente ao início do relógio do supervisor.
Este deslocamento aplica-se igualmente ao início e ao fim de cada forward no
mesmo braço. Nenhuma subtração usa carimbos absolutos de origens diferentes.

A amostragem é sequencial. O supervisor lê io.stat e depois o contador do
namespace, antes do carimbo final da amostra. Cada leitura pode ter ocorrido
em qualquer instante desde o carimbo anterior até ao atual. As 57 amostras
D0 e 39 amostras D1 incluem janelas de até 2,087 s e 1,079 s. Com um
alinhamento fixo, duas observações cujas janelas inteiras caem dentro do
forward estabelecem um mínimo pelo crescimento entre elas. Para o máximo
usam-se observações inteiramente antes e depois, ou o delta global, incluindo
a incerteza do contador inicial absoluto. O programa varre as fronteiras em que
muda a classificação das amostras, incluindo empates. Retém o mínimo e máximo
sobre todos os alinhamentos inteiros admissíveis. [Supervisor e ordem das leituras](../admission/profile.py#L158) · [Cálculo dos limites](bounds.py)

O teste sintético cobre leituras atrasadas, regressão de contador, deltas
incoerentes, baseline absoluta não nula e um oráculo exaustivo de duas chegadas
em nove instantes sob várias janelas e deslocamentos. O verificador reabre os
digests e o censo de cada braço com o auditor já usado no projeto. Os caminhos
originais e a cópia independente da parte 131 deram, byte a byte, o recibo
`561b2226184e1ae97d0c73a929aa0c014ab538b2235a7669d587083bf67e1f5d`.
[Auditoria de origem](../cost/review.py) · [Testes](test_bounds.py)

```sh
python3 -IB -m unittest discover -s .
python3 -IB bounds.py --d0 "$D0" --d1 "$D1" --new-output "$NEW_DIR"
```
