# Uma seleção inicial para o tempo e o volume de T2

**NO_GO para 239 entradas com as durações de leitura R0 e o denominador contratual de 47 saídas.** O menor conjunto que permite aos dois pisos passar tem 247 chaves. Mesmo escolhendo as melhores 239 com conhecimento de T2, a restrição de volume faz o piso temporal subir para 10,103767 s. A cache de 353 deixa margem para investigar se T1 pode disponibilizar as identidades necessárias. A preparação, a latência de entrega e o efeito no primeiro pedido continuam por medir. M4 permanece **NOT_MET**. [Recibo das duas reproduções](joint-r01.json) · [Pré-registo](joint-protocol.md)

| Denominador e escala dos READ | Mínimo conjunto e repartição prefill + decode | Melhor piso com uma chave a menos | Piso no mínimo | Piso K=239 | Piso K=353 |
|---|---:|---:|---:|---:|---:|
| M4, 47 saídas, 1× | **247 = 224 + 23** | 10,007450 s | 9,994367 s | **10,103767 s** | 8,913188 s |
| M4, 47 saídas, 0,8× | 224 = 224 + 0 | volume excedido | 9,507039 s | 9,282393 s | 8,329929 s |
| Sensibilidade, 46 avaliações, 1× | 219 = 167 + 52 | 10,003822 s | 9,992413 s | 9,772898 s | 8,868601 s |
| Sensibilidade, 46 avaliações, 0,8× | 167 = 167 + 0 | volume excedido | 9,788543 s | 9,017698 s | 8,294260 s |

**TRACE_DERIVED.** No journal do segundo pedido, 567 das 875 chaves temporais pertencem ao conjunto das 1051 chaves de serviço do prefill. Todas as 567 entram nas duas chamadas de prefill. As restantes 308 entram em callbacks de decode antes do primeiro conteúdo final. A interseção dessas 308 com as 1051 é vazia. Há 484 chaves que podem ajudar apenas o piso de volume. O verificador confronta chaves e gerações, contagens por dispositivo e os dois extremos de cada callback com o relógio do cliente, conservando a folga de 1 ms. [Reconstrução e DP](joint.py) · [Enumeração exaustiva](test_joint.py)

Por fase, o algoritmo calcula o menor custo restante para cada número de chaves temporais disponíveis. Para cada par de cardinalidades acrescenta as chaves de efeito exclusivamente volumétrico indispensáveis. Reconstrói a seleção e volta a somar os pisos das waves e os bytes para confirmar que **a mesma seleção** justifica cada linha da tabela. Nenhuma das quatro seleções mínimas precisou de usar as 484 chaves exclusivamente volumétricas. Os hashes das seleções e a repartição em cada capacidade estão no recibo. A escolha pode mudar entre linhas. [Prova do custo por wave](README.md)

No contrato de 47 saídas o piso de volume nas seleções da tabela é 10 932 278 400 B, apenas 6 088 406 B abaixo do orçamento baseado em 4,5 GB/s. No caso de 46 avaliações, sobram 2 594 007 B entre o piso de 11 685 772 800 B e o orçamento. Com serviço a 1×, o caso M4 exige no mínimo 3 265 142 400 B de experts exatos preparados antes de T2 e a sensibilidade de 46 avaliações exige 2 895 004 800 B. A 0,8× esses mínimos são 2 961 100 800 e 2 207 606 400 B. O custo adicional em T1 depende de que experts já tinha de ler e de quanto custa reter e entregar as cópias. Mesmo 353 entradas requerem um envelope de RAM adicional de 4 720 263 168 B segundo o crivo de capacidade. [Orçamento e montagem da L2](../host_cache/README.md)

O cálculo concede a seleção ideal antes de T2, cache ilimitada após esse instante e redução gratuita do READ das chaves escolhidas. O alvo continua a selecionar e a consumir os mesmos experts. Cada valor temporal é um limite inferior de wall na família congelada, com 5,996896 s de custo exterior preservado. A escala 0,8× é uma sensibilidade uniforme aplicada às leituras observadas. Um teste causal terá de estabelecer que identidades T1 realmente pode colocar, quando os bytes ficam disponíveis e o custo de preparação no turno anterior. Atribuir os tempos ao produto requer ainda a agenda executada, os pares de casos e proteção do primeiro decode. [Âmbito do piso](../mandatory.md)

## Reprodução

A adenda foi congelada em `2ed5c725`. O solver tem SHA-256 `09bf654fb3328fad7c41a0895869ef157470aa9ddd8b1a982fbcd82c0ed4ff1f` e os testes `7eade504bf3e1a2b0cc0f548b7d4c6462ec90ae76516da1019e0df39791ce84f`. Os seis testes dos dois estudos passaram antes da análise. Cada reprodução abriu uma cópia autenticada do plano e o mesmo journal, em processos separados e com destino exclusivo. R01 e R02 duraram 0,31 s cada e usaram 46 816 e 46 868 KiB de RSS máximo. O recibo é idêntico byte a byte, SHA-256 `5eea9fd586bb4c56d63964ed75184f73d06b44d2d5ee9d6e428cbc014ff76ce2`. A carga foi integralmente CPU, sem pesos.

```sh
STUDY=research/qualification-retake/phase_fd/integrated/warm_oracle
python3 -IB -m unittest discover -s "$STUDY" -p 'test_*.py'
timeout 120s prlimit --as=536870912 --cpu=120 --fsize=1048576 -- \
  python3 -IB "$STUDY/joint.py" --plan-dir "$PLAN" --on-dir "$ON" --new-output-dir "$NEW"
cmp "$NEW/receipt.json" "$STUDY/joint-r01.json"
```
