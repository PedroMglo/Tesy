# Margem de serviço para reabrir a via de prefill no C163

**5,1494% é a menor redução uniforme, na grelha testada, que leva o teto a 10% em ambas as execuções.** A hipótese reduz por igual o serviço LOAD_BEGIN→LOAD_END das 851 leituras retidas. Mantém os relógios e dependências de cada braço e concede despacho ideal, ausência de custo de reposição e eliminação das 50 leituras. Uma redução real de duração concentrada nalguns serviços terá de ser avaliada pela sua identidade e posição nas barreiras. A média das durações, por si só, não decide o resultado.

| Cenário | Primeiro p em ON-1 | Primeiro p em ON-2 | Primeiro p comum | Margem ON-1 ao p comum | Margem ON-2 ao p comum |
|---|---:|---:|---:|---:|---:|
| Trabalho fora de WAIT fixo | 5,1494% | 4,9654% | 5,1494% | +1,4 µs | +9 090,1 µs |
| Interior observado dos callbacks grátis | 5,1436% | 4,9601% | 5,1436% | +0,4 µs | +9 059,1 µs |

A resolução da grelha é 0,0001 ponto percentual. A 5,1493%, ON-1 ainda fica 0,6 µs aquém do corte no cenário fixo. A 5,1494%, o teto chega a 0,905954 s em ON-1 e 0,914980 s em ON-2. As margens subtraem o corte de cada braço ao seu próprio teto de parede. Sem alterar o serviço, os défices correspondentes são 252 807,6 e 245 726,9 µs. O resultado é condição de possibilidade dentro desta família de reduções, sem previsão de execução. [Protocolo da sensibilidade](margin_protocol.md) · [Recibo](margin-evidence/receipt.json)

Como verificação exploratória, para cada uma das 851 identidades tomámos a menor duração observada entre ON-1 e ON-2, deixando intactas as releases, deadlines e o relógio do braço em avaliação. Isto encurta 435 e 416 jobs e retira 691 423 e 812 656 worker-µs, respetivamente. Ainda faltam 39 612,6 e 7 207,9 µs de parede para o teto alcançar o corte de 10% com non-WAIT fixo. Medir o candidato envolve verificar se este altera a duração e colocação no caminho crítico das leituras retidas sob concorrência real. Os mínimos históricos podem ter ocorrido em condições incompatíveis entre si.

A procura programática verifica por inteiros os dois pontos de grelha adjacentes. A duração mínima de cada leitura desconta primeiro 1 µs de resolução e o produto da escala arredonda por defeito. Assim o teto favorece a hipótese de redução. As ordens EARLY e LATE produziram as mesmas janelas. Quatro testes cobrem os extremos, o emparelhamento de identidades e o arredondamento por job. Os três ensaios produziram o mesmo recibo em 5,20 s acumulados, com pico de 129 624 KiB e sem modelo ou GPU. [Cálculo](service_margin.py) · [Testes](test_service_margin.py)

```sh
out=$(mktemp -d)
python3 research/prepin44/service_margin.py --raw-dir "$TESY_C163_RAW" --new-output-dir "$out/margin"
```
