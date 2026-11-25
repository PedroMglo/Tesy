# Preço das leituras ao longo de todo o decode

**MEDIDO no portátil.** Ao servir a população inteira de leituras do decode deste pedido, o pack do Tesy poupou **1,333 e 1,279 s** nas duas ordens. Ambos os layouts estavam no NVMe interno e continham os mesmos bytes de pesos. A soma das barreiras baixou em **23,73% e 22,85%**, com ganho em todos os 46 passos de cada par. O controlo e o candidato de armazenamento fizeram 2 391 e 797 preads por travessia, respetivamente. [População, clocks, recursos e custos de preparação](service/README.md) · [Recibo da reprodução](service-evidence.json)

**GO para avaliar o pack com entregas reais ao primário. INCONCLUSIVE para a conversa.** No cenário que cobra os SET do controlo com correspondência neste pedido, o pack deixa 716–749 ms para todos os custos adicionais antes de perder os 6 tok/s. Sob os preços de prefill congelados, mesmo conceder custo zero a esses trabalhos ainda deixa 1,125–1,158 s por recuperar para o primeiro conteúdo final em 10 s. O sinal positivo do serviço e o NO_GO para suficiência sob estas hipóteses coexistem. O alvo é uma única configuração que passe os dois relógios, a exatidão, os dois workloads e os critérios completos de produto.

| Ordem no processo | Layout | Soma do despacho à barreira (s) | Teto só com READ (tok/s) | Teto com READ e SET comum (tok/s) | Margem para 6 tok/s (s)¹ | Margem conjunta (s)¹ |
|---|---|---:|---:|---:|---:|---:|
| 1.º, R→P | GGUF | 5,616923 | 5,948 | 5,586 | −0,581 | −2,455 |
| 2.º, R→P | pack | 4,283907 | 7,152 | 6,634 | +0,749 | −1,125 |
| 1.º, P→R | pack | 4,318643 | 7,117 | 6,604 | +0,716 | −1,158 |
| 2.º, P→R | GGUF | 5,598015 | 5,963 | 5,599 | −0,561 | −2,435 |

¹ **ESTIMADO.** As duas margens usam READ+SET comum. A margem positiva mais apertada corresponde a **0,716474 s por pedido**, ou **0,599 ms por admissão** se repartida igualmente pelas 1 196 admissões. É um orçamento de parede no caminho crítico. Cada SET pode sobrepor-se a trabalho de outro worker. Só os 969 SET do mesmo sítio e expert em R0 têm preço observado. Os restantes 227, a procura no banco, a contenção, a publicação e o drain do candidato requerem medição. Mesmo com todas as entregas gratuitas, só com os tempos de READ do pack ainda faltam **0,612 e 0,645 s** para a meta conjunta neste cenário.

O pack tinha ficado aquém do limiar de adoção isolada da C293, com 7,47% no nominal e 6,05% em código. Conservá-lo permitiu testar o ganho marginal depois de mudar a política de cache. As percentagens usam denominadores diferentes. Para decidir a adoção, contam o controlo contemporâneo, o candidato completo e a ablação que desativa cada componente na mesma agenda. Os sinais dos pares, a proteção de código, a construção do banco em T1 e o custo de chegar ao primeiro decode continuam a entrar no avaliador. [Decisão da C293 e critérios da conversa](../../../../../../../../packed_nvme_manifest/server_profile/product-protocol.md)

Em cada ordem houve ganho em 621 e 617 dos 632 grupos que pediram bytes ao disco. As diferenças medianas por grupo foram 2,286 e 2,300 ms. A redução nas camadas CPU somou 0,884 e 0,829 s, e nas camadas CUDA 0,449 e 0,450 s. Estas categorias identificam o consumidor lógico. Os quatro braços leram até RAM. Os 1 024 grupos sem nova leitura mantiveram o seu lugar na contabilidade. Os dois pares partilham as mesmas rotas de um único pedido nominal. Os sinais e a dispersão descrevem essa população. Ainda falta medir a configuração integrada com os dois casos e a sessão sustentada.

A intervenção reduz o número de experts que precisam do NVMe. Para testar se a organização dos pesos também ajuda, os dois layouts têm de servir os mesmos 797 experts nos mesmos sítios do pedido. As 399 admissões servidas pelo banco continuam a precisar de chegar ao primário. Em 227 casos a admissão só existe na política alternativa, pelo que o seu custo de SET não tem preço observado nesse sítio do controlo. O T2 natural R02 fornece 1 656 callbacks das 46 avaliações de uma posição e 47 saídas no contador do servidor. O ensaio usa quatro workers no portátil e lê os pesos originais para RAM. [Preparação exclusiva a partir do replay](preparation.md) · [Contrato da medição](service/protocol.md) · [Verificação independente](review-protocol.md)

Para estimar o custo da conversa, conservar o exterior de R0 (2,318241276 s) e reconstruir separadamente o serviço de cada grupo. O preço mais favorável só cobra a duração das leituras. O seguinte acrescenta os SET observados de cada admissão comum à sua própria cadeia e concede preço zero aos 227 SET desconhecidos. Em cada grupo com até quatro jobs, vale a cadeia mais longa. Os grupos de posições e camadas sucessivas são sequenciais. Uma terceira sensibilidade substitui a duração da callback inteira pelo tempo de despacho até à barreira da fixture de leitura, com todas as entregas gratuitas. Os tetos do decode são 7,833333334 s a 6 tok/s e 5,959223099 s para compensar o preço de prefill da política nesta captura. Antes dos SET e da coordenação, isto deixa 5,515092058 e 3,640981823 s por cobrar dentro das callbacks. O preço do prefill pressupõe 4,5 GB/s úteis e as lacunas intercamadas observadas. [Orçamento das duas fases](../../../accounting.md) · [Preços das operações observadas em R0](../README.md)

## Reprodução e conservação

O protocolo físico foi registado em `a37e2c6a`, o programa de medição em `0224d266` e a revisão independente em `d8d295e4`, `bba48a9e` e `7b870af7`. Duas revisões CPU independentes (0,11 / 0,13 s, RSS até 30 524 KiB) deram o mesmo recibo. Uma terceira leitura da cópia arquivada confirmou o mesmo SHA-256 `27832256db8ae629ece5c8d95f1ce5e0d285c24cfddf3b7e110b92154ad4cbc1`. A parte 65 conserva o plano, as duas admissões C55 recusadas e a parte 66 conserva a C55 admitida, os dois processos e as duas revisões. O manifesto da parte 66 cobre 18 ficheiros, 2 706 885 B, SHA-256 `de926e27af098ac21015917772c36f5357496c3e1604b121b371e1ec5e2979e7`. [Comandos físicos e identidades do modelo e do pack](service/README.md)

```sh
t=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/replay/decode_clock/transport
python3 -IB "$t/review_service.py" \
  --plan "$PART65/tesy-decode-transport-prepare-20261125-r01/plan.json" \
  --plan-sha256 aed09397a16ed706365d73e0d2535427528476b41d66e3d5e43ad90da345d79a \
  --first "$PART66/tesy-decode-service-20261125-r01" \
  --first-sha256 1ac4bb4e666b61898cbb655cddb24d771529e71d66515e56862b989434b76e57 \
  --second "$PART66/tesy-decode-service-20261125-r02" \
  --second-sha256 acd29327feb616f130f9518e67f39d1bc69e692f896352706dd4ed2a13a49e98 \
  --new-output-dir "$NEW"
```
