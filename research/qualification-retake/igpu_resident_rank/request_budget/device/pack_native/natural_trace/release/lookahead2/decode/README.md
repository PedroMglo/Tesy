# Uma camada de antecedência nos dois relógios de T2

**O cenário otimista admite as duas metas, mas no P106 sobram apenas 684,248 ms até ao primeiro final se a previsão começar no RANKS observado, a ligação servir 4,5 GB/s úteis e os SET conservarem os próprios preços.** A margem de decode é 3 345,304 ms. O relógio de 10 s limita a combinação. Sem previsão, mesmo com SET gratuito e as restantes concessões, o primeiro final excede 10 s por 1 324,868 ms no P106 e por 64,494 ms no P97 à mesma taxa. A 8 GB/s, só o banco já admite uma margem de 492,404 ms no primeiro final do P106 sob essas concessões. As taxas são cenários de transporte partilhado; os dois pedidos foram observados com a política R0. [Recibo das duas trajetórias](receipt.json) · [Pré-registo](protocol.md)

### Qual trabalho se consegue atribuir

As duas trajetórias têm 1 440 slots READY iguais no início do decode e 1 656 remaps de uma linha. **Todas as 1 091 reservas de decode** pertencem a uma procura dos quatro ranks da própria avaliação e camada. Cada geração tem a sua reserva, ENQUEUE de demanda, 1 READ do pack e 3 SET no mesmo worker, publicação e conclusão dentro do respetivo remap. O selo das identidades por geração, sítio e hit do banco coincide entre processos. A unidade é a reserva de uma geração, incluindo recargas da mesma chave. O FREQ353 foi selado antes do POST T2 em P106; a análise transporta essa seleção para a trajetória homóloga P97. [Revisor de serviço](../../../prefill_retention/request_cost/score.py) · [Seleção do T1](../../../prefill_retention/README.md)

| Fase T2 | Reservas R0 | Cobradas | Pack CPU / CUDA | Banco CPU / CUDA | Payload de pack cobrado |
|---|---:|---:|---:|---:|---:|
| Prefill, calls 1–2 | 1 263 | 567 | 274 / 143 | 101 / 49 | 5 512 406 400 B |
| Decode até à primeira peça, calls 3–46 | 1 067 | 1 067 | 733 / 264 | 40 / 30 | 13 179 542 400 B |
| Decode depois, calls 47–48 | 24 | 24 | 12 / 6 | 1 / 5 | 237 945 600 B |

O primeiro final vem da amostra 45 no RETURN 46. Em P97/P106 o limite entre esse RETURN e a emissão observada é 3,665/3,595 ms. Nenhuma callback das duas últimas avaliações antecede o primeiro final. O relógio do cliente, 18,326/19,529 s em R0, inclui o prefill e 44 avaliações relevantes. O decode nativo de 8,947/9,214 s inclui as 46 avaliações; o denominador do servidor é de 47 tokens, contando a saída do prefill. P106 inclui a selagem que ocorreu antes do stream. As janelas de previsão e os SET de cada pedido usam o seu próprio relógio. [Ligação entre token, RETURN e SSE](../../../client_cut.py)

### Margens simultâneas para trabalho ainda por pagar

Cada par da tabela dá a **margem do primeiro final / margem de decode**, em ms. Uma previsão de largura quatro por destino é perfeita nesta relaxação, e cada alvo do decode tem no máximo quatro experts nessa avaliação. No prefill, quatro por destino e tile restringe o total mesmo quando há várias posições. O recibo contém também largura ilimitada no prefill. L0 espera pela procura. A coluna de SET a preço observado exige que os três SET de cada job só comecem no remap da procura. Por avaliação cobra-se o maior entre o piso do link e o piso dos SET, somando neste último os pisos dos remaps sucessivos de quatro workers. Esta sensibilidade ainda oferece concorrência ideal entre recursos.

| Pedido | Início da previsão +1 | GB/s | SET gratuito | SET a preço observado |
|---|---|---:|---:|---:|
| P97 | Fronteira anterior otimista | 4,5 | 2 257,781 / 3 946,661 | 2 246,424 / 3 941,942 |
| P97 | RANKS observado | 4,5 | 1 821,324 / 3 523,160 | 1 821,324 / 3 523,160 |
| P106 | Fronteira anterior otimista | 4,5 | 1 126,820 / 3 775,936 | 1 105,618 / 3 768,633 |
| P106 | RANKS observado | 4,5 | 686,346 / 3 347,212 | **684,248 / 3 345,304** |
| P97 | Fronteira anterior otimista | 8 | 3 475,306 / 5 031,073 | 3 170,850 / 4 856,856 |
| P97 | RANKS observado | 8 | 3 231,125 / 4 785,520 | 3 053,763 / 4 739,432 |
| P106 | Fronteira anterior otimista | 8 | 2 262,208 / 4 781,951 | 1 846,454 / 4 514,022 |
| P106 | RANKS observado | 8 | 2 030,874 / 4 549,952 | 1 791,754 / 4 459,321 |

No P106 a 4,5 GB/s com RANKS, a ligação pode antecipar até **4,333 GB no prefill, 4,718 GB nas primeiras 44 avaliações e 0,103 GB nas últimas duas**. Os pisos de rede exposta são 262,186, 1 880,365 e 29,888 ms. A contracção dos remaps retira 5 875,564, 6 481,902 e 156,076 ms das três fases. O cálculo não reutiliza estes intervalos como tempo disponível para transporte. EDF dá precedência ao prazo mais próximo e disputa uma única ligação para CPU e CUDA. Remover outras esperas, mudar a sequência de reservas ou alterar o cache muda as janelas do problema. [Método EDF e fronteiras da fonte](../README.md)

**Como usar o limite.** Em ms, seja p o custo exposto só no prefill, x o custo novo até à primeira peça nas 44 avaliações, e y o custo novo nas duas últimas. No cenário P106 assinalado é necessário satisfazer **p+x ≤ 684,248 e x+y ≤ 3 345,304**. Se todo o acréscimo estiver antes da primeira peça, o saldo menor limita x. As 696 reservas de prefill fora do conjunto estrito incluem 147 hits adicionais de banco e **549 entregas do pack**, 7 257 340 800 B úteis. Se consumirem toda a margem de 684,248 ms, isso permite em média apenas **1,246 ms novos expostos** por uma dessas 549 entregas, com custo adicional zero para tudo o resto. Trata-se de tempo exposto além do que o link já paga. Uma leitura antecipada pode sobrepor-se a trabalho existente. Para decidir a admissão de timing, identificar custo e prazo no mesmo destino para essa população, os falsos positivos e a parte exposta de materialização, sincronização e verificação; uma soma acima da margem exclui a combinação nesse cenário.

Uma projeção densa por camada no decode executaria 1 610 pares posição/destino, **593 510 400 MAC**, mais 529 920 B se o operando cruzar a fronteira CPU/CUDA nas 46 avaliações. Com o prefill, são 6 813 pares e **2 511 544 320 MAC**. As mesmas 35 matrizes podem servir ambas as fases. A aquisição FREQ no T1 exigiria 1 126/423 cópias CPU/CUDA e as reposições no decode são 41/35. O custo em segundos do predictor, do banco e dos erros de previsão continua por medir. A concordância de ranks no C270 sobre quatro posições não fornece recall dos misses deste pedido. Os 8,487 tok/s da análise anterior referem-se a prefill +2 de largura ilimitada, com toda uma poupança hipotética do decode antes da primeira peça; aqui o decode é precificado por geração com +1. [Volume e aritmética de prefill](../README.md)

### Reprodução offline

Protocolo `92cf02b4`, fonte e quatro testes `1d0abd8b`. Duas execuções de 2,50/2,51 s, RSS 59 064/59 860 KiB, produziram os mesmos 32 170 B, SHA-256 `2c8b361af5ecf04e09643040841ea4d7f59cb0796153b10545367b8f17deacf3`. Cada execução também reconstituiu byte a byte o recibo integral de prefill. Os caminhos abaixo usam as partes privadas e a checkout C291 originais. [Código](screen.py) · [Testes de causalidade e recursos](test_screen.py)

```sh
python3 -IB test_screen.py
timeout 90 prlimit --as=536870912 --cpu=90 -- python3 -IB screen.py \
  --archive "$PARTS" --backend "$C291" --new-output-dir "$FRESH/r01"
timeout 90 prlimit --as=536870912 --cpu=90 -- python3 -IB screen.py \
  --archive "$PARTS" --backend "$C291" --new-output-dir "$FRESH/r02"
cmp receipt.json "$FRESH/r01/receipt.json" && cmp receipt.json "$FRESH/r02/receipt.json"
```
