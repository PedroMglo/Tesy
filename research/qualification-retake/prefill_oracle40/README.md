# Que poderia poupar uma cache ideal antes da primeira chamada?

**INCONCLUSIVE para a colocação causal.** Com 40 slots por camada e liberdade para escolher gratuitamente o conteúdo inicial olhando para todo o prefill nominal C135, bastariam **378 faltas** em vez das 1 222 gerações observadas. Este é o mínimo do problema de residência especificado. A ordem de waves acrescenta cinco cargas ao piso de 373 que a contagem de distintos já impunha. O ótimo exige uma escolha de entrada informada por procuras posteriores. [Pré-registo](protocol.md) · [Cálculo por camada](evidence/receipt.json)

| Tier | Gerações de R0 na call 5 / 148 | Distintos em 5+148 por camada, somados | Mínimo por cardinalidade | Ótimo com as waves |
|---|---:|---:|---:|---:|
| CPU, 25 camadas | 37 / 761 | 1 245 | 254 | 254 |
| CUDA, 11 camadas | 8 / 416 | 514 | 119 | 124 |
| Total | 45 / 1 177 | 1 759 | 373 | **378** |

A escolha inicial que dá primazia às primeiras utilizações admite todas as demandas da call de 5 sem leituras adicionais. A residência atravessa o retorno. Na call de 148 cada wave mantém os seus experts simultaneamente, com substituição offline por uso futuro mais distante. O ponto de emissão DEMAND do C122 cobre também os hits. O pedido natural deixa o FFN35 podado em toda a call de 5 e nos primeiros quatro tiles da call de 148. Só a posição final, 2196, percorre esse FFN. O verificador reconcilia as 35 waves da primeira call e as 277 da segunda, os 36 conjuntos distintos e as 1 177 gerações da segunda com a reconstrução independente do #45. A ordem dos ranks por token, os planos físicos, os pins de parking, a reconstituição do estado de decode e as dependências do cliente conservam qualificações próprias.

O mínimo equivale a 4 996 857 600 bytes de pesos originais. No cenário de 4,5 GB/s úteis restariam **1,317 s** dos 2,427 s para todo o restante prefill. Para cumprir esse orçamento cabem até 826 cargas. R0 teria de evitar pelo menos 396, mesmo que a leitura fosse o único custo. Eliminar as 184 recargas entre tiles deixaria 1 038. O SSD interno é um Micron 2400 de 1 TB. O fabricante especifica 4 500 MB/s em leitura sequencial de 128 KB, QD32, unidade nova. Esse valor define um cenário de engenharia. A largura PCIe observada e o benchmark de leituras de experts têm métricas distintas. As contas pertencem ao C135 com decode ajustado a exatamente 6 tok/s, não constituem uma medição de M4. [Condições de teste da Micron](https://www.micron.com/content/dam/micron/global/public/products/product-flyer/2400-ssd-product-brief.pdf) · [Piso de serviço com os tempos do próprio C135](../prefill_read_floor/README.md)

**Proveniência e reprodução.** Pré-registo 72a8b664, código final 4f9fcf25b97f555a90e0ebf2069e07054b87620e, árvore 47104576ca788bbb8cbf741f30378ff35e530bf5. A primeira execução excedeu o limite de alocação ao inicializar a threadpool de OpenBLAS antes de chegar ao leitor. A segunda usou uma thread e parou na cobertura do grafo. A suposição inicial de saída na call de 5 era de outro harness. Verificámos os flags de logits no servidor, o nó de seleção de linhas na fonte pinada e os intervalos de posições no journal antes de corrigir o validador. As duas reproduções seguintes levaram 0,37 e 0,40 s, com até 88 656 KiB de RSS, e emitiram o mesmo SHA-256 b7617360fd299718ce823c2972fd87bcff3cd73d7e1520f2088c2187cded032a. Seis testes sem modelo, incluindo a enumeração de pequenos estados. Sem leitura de pesos ou GPU. [Falha de inicialização](evidence/r01-failure.json) · [Falha de cobertura](evidence/r02-failure.json)

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120 prlimit --as=536870912 -- \
  python3 -B research/qualification-retake/prefill_oracle40/screen.py \
  --trace "$C135_TRACE" --backend "$C122" --pr45-checkout "$PR45" --new-output-dir "$NEW_OUT"
```
