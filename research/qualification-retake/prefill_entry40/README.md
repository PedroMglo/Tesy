# O que se pode ganhar quando o pedido já começou?

**NO_GO condicionado para mudar apenas as vítimas durante o prefill C135.** A partir do estado que o pedido encontrou, 40 slots por camada exigem **pelo menos 874 cargas**, mesmo com acesso ao futuro, reconstituição final gratuita e sem custo de cálculo. Ao preço de cenário de 4,5 GB/s, as leituras exigiriam 2,567 s. O próprio C135 admite 2,427 s de prefill para entregar o primeiro conteúdo final em 10 s quando o decode atinge exatamente 6 tok/s. Faltariam pelo menos 48 cargas ou 140 ms, mesmo concedendo todo o orçamento ao disco. A taxa mínima seria **4,760 GB/s de payload útil**. [Protocolo](protocol.md) · [Resultado, snapshots e 36 camadas](evidence/receipt.json)

| Tier | Slots identificados / desconhecidos | Distintos em falta, concedendo as melhores incógnitas | Piso das waves com essas concessões | Piso pela fronteira da call 148 | Piso combinado por camada |
|---|---:|---:|---:|---:|---:|
| CPU | 986 / 14 | 553 | 567 | 563 | 577 |
| CUDA | 438 / 2 | 287 | 297 | 291 | 297 |
| Total | 1 424 / 16 | 840 | 864 | 854 | **874** |

O journal permite ligar cada identidade a uma versão de slot através das substituições e dos hits READY. Dos 1 424 residentes identificados antes da primeira procura, 904 foram pedidos e 520 ficaram fora do conjunto utilizado. Demos aos slots desconhecidos as identidades úteis com primeiro uso mais próximo, 15 ao todo. Se nenhum dos 16 slots desconhecidos ajudar, o mínimo do problema lógico de waves sobe de 864 para 879. A reconstrução coincide posição a posição com a prova do #45 à entrada e à saída da call de 148, incluindo as incógnitas.

Há uma segunda forma de limitar o ganho. No registo, a primeira call admitiu exatamente os 45 experts em falta e conservou todos os selecionados até ao retorno. Para uma agenda que parta do mesmo estado, cada leitura adicional na primeira call pode acrescentar no máximo uma identidade nova útil à entrada de 148. Preservar um residente que R0 expulsou pode poupar outra leitura, mas as 45 substituições são debitadas pelas 45 primeiras faltas obrigatórias. O verificador prova estas condições por camada e reconcilia o número mínimo de cargas do #45 para a segunda call. A soma do maior dos dois pisos **em cada camada** produz 874. Este é um limite inferior; não há uma agenda física demonstrada com precisamente esse custo.

O estado livre estudado em paralelo só precisa de 378 cargas no mesmo problema de waves. Essa diferença aponta para outra intervenção: preparar residência antes de o pedido incremental chegar e cobrar o custo ao prefixo que a produziu. Mais largura de banda útil, uma fonte de bytes já disponíveis, um decode acima de 6 tok/s, outro trajeto de geração ou outro grafo qualificado também mudam o cenário. A Micron publica 4,5 GB/s para leitura sequencial a QD32 de uma unidade nova. A taxa publicada difere da taxa efetiva do workload de R0. O NO_GO é específico da hipótese quantitativa e deste único pedido trace-ON. [Entrada gratuita e contagens](../prefill_oracle40/README.md) · [Micron 2400, tabela e método](https://www.micron.com/content/dam/micron/global/public/products/product-flyer/2400-ssd-product-brief.pdf)

Pré-registo 94d7ef66, commit de confirmação 974b55498516060a528da231e494143fc454871d, árvore f71987c78cda83161d329e263f2e3747e47c1046. Duas reproduções de 0,54 e 0,52 s com até 88 808 KiB de RSS devolveram o mesmo recibo SHA-256 16291c82a97afeb320d537e7be81dddf8833b583add98ffcf868666dd1ce4901. Três testes locais exercitam as versões de slot, o custo de transição e a escolha de incógnitas contra 1 512 soluções por programação dinâmica. Zero pesos lidos, zero forwards e zero compute GPU.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120 prlimit --as=536870912 -- \
  python3 -B research/qualification-retake/prefill_entry40/screen.py \
  --trace "$C135_TRACE" --backend "$C122" --pr45-checkout "$PR45" --new-output-dir "$NEW_OUT"
```
