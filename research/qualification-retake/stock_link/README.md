# Quanto tráfego teria de chegar à GPU durante o decode?

**FORMAL, condicional às rotas C294. O teto bruto do PCIe permite continuar a avaliar o stock.** Nas 36 camadas, mesmo com escolha ótima dos 161 experts iniciais e das vítimas futuras, manter seis passos/s exige fornecer à cache CUDA pelo menos **6,080 GB/s** no nominal e **5,604 GB/s** em código. Se os quatro experts de cada camada faltarem sempre, o requisito sobe a 11,421 GB/s. O endpoint da RTX 4060 Laptop e a ponte upstream anunciam ambos 16 GT/s × 8 lanes. O teto bruto favorável usado no protocolo é 16 GB/s num sentido, antes da codificação e dos restantes custos do PCIe. [Protocolo](protocol.md) · [Quatro journals verificados e resultados por braço](run-01/receipt.json)

| C294, 32 passos fornecidos | Cargas mínimas com futuro conhecido | Payload mínimo RAM→GPU | Percentagem do teto bruto a 6 passos/s |
|---|---:|---:|---:|
| nominal153, braço 2 | 2 453 | 32 426 697 600 B | 38,00% |
| nominal153, braço 3 | 2 453 | 32 426 697 600 B | 38,00% |
| code153, braço 2 | 2 261 | 29 888 611 200 B | 35,03% |
| code153, braço 3 | 2 261 | 29 888 611 200 B | 35,03% |

Nos quatro braços a hipótese de zero hits requer 4 608 cargas, 60 914 073 600 B e 71,38% do teto bruto. Os extremos têm pressupostos distintos da política real ClassLRU. A prova usa apenas os quatro experts selecionados por grupo no R0. O stock pode selecionar outros IDs e o estado da sua cache depende do prefixo. O seu ensaio de arranque observou 262 faltas e 3 463 430 400 B de payload em duas posições internas. Para atribuir tempo ao transporte numa conversa, faltam o serviço efetivo das cópias dependentes, a residência das páginas de origem e o seu lugar no caminho crítico. A janela de 32 passos fornecidos tampouco identifica tok/s confirmados pelo cliente. [Marcadores de arranque](../stock_log/README.md) · [Comparação de logits](../stock_numeric/README.md)

O cálculo partiu de 277834e3 após congelar os critérios em 34d7a84f. Custou menos de um segundo de parede, sem carregar o modelo nem usar compute CUDA. O solver de conjuntos com pins foi verificado por enumeração em instâncias pequenas. [Testes do solver](../test_cache_bound.py)

```sh
python3 -B research/qualification-retake/stock_link/bound.py --raw-dir "$TESY_C294_RAW" --new-output-dir "$NOVO_DESTINO"
```
