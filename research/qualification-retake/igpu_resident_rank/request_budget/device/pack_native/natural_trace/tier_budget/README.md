# Que parte do primeiro final e do decode depende do remap de cada destino?

**TRACE_DERIVED.** No P com pack, apagar os remaps das camadas CPU em todas as fases deixa 90,641 ms de margem para o primeiro conteúdo final. Teria de desaparecer pelo menos **98,923%** da união CPU antes dessa peça. Na referência C269 com GGUF, a mesma concessão ainda deixa um défice de 798,202 ms. Uma mudança limitada aos intervalos CUDA falha o alvo de primeiro final nos dois braços. O alvo de decode isolado tem margem otimista em ambos os destinos. Estes são limites no mesmo pedido observado em cada braço. [P com pack](evidence/packed.json) · [Referência C269](evidence/c269.json)

| Braço e intervalos apagados | Máximo poupável no primeiro final (s) | Piso do primeiro final (s) | Máximo poupável no decode (s) | Piso do decode de 47 saídas (s) | Alvos simultâneos |
| --- | ---: | ---: | ---: | ---: | --- |
| C269 · CPU | 9,687339 | 10,798202 | 5,390986 | 4,612791 | NO_GO |
| C269 · CUDA0 | 4,800307 | 15,685235 | 2,248305 | 7,755472 | NO_GO |
| C269 · ambos | 14,487646 | 5,997896 | 7,639291 | 2,364486 | HEADROOM_ONLY |
| P · CPU | 8,416202 | 9,909359 | 4,732211 | 4,214415 | HEADROOM_ONLY |
| P · CUDA0 | 3,998631 | 14,326930 | 1,936242 | 7,010384 | NO_GO |
| P · ambos | 12,414833 | 5,910728 | 6,668454 | 2,278172 | HEADROOM_ONLY |

Cada braço tem 2 987 intervalos completos. No C269 os relógios mediram 20,485541 s para o primeiro final e 10,003777 s de decode. Mesmo com CUDA gratuita seria preciso eliminar outros 5,685235 s no destino CPU, 58,69% da união CPU até ao primeiro final e 58,13% da união CPU dos dois relógios. Com CPU gratuita, os restantes 798,202 ms correspondem a 16,63% da união CUDA antes do primeiro final e 16,33% da união CUDA dos dois relógios.

No P os relógios mediram 18,325561 s e 8,946626 s. Com CUDA gratuita, o mínimo adicional na CPU é **4,326930 s**, 51,41% da sua união antes do primeiro final e 50,95% da sua união nos dois relógios. No cenário CPU gratuita, os 8,416202 s até ao primeiro final dividem-se em 3,760636 s de prefill e 4,655566 s durante o decode até à amostra 45. Se uma combinação apenas conseguir o requisito de **6 tok/s** no decode, pode comprar no máximo 1,113293 s nessa fase; concedendo todo esse ganho antes da peça final, juntamente com todas as callbacks CPU do prefill, o primeiro final ainda demoraria **13,451632 s**. A margem de 90,641 ms exige ganhos muito maiores no decode até à amostra 45.

O verificador concede a eliminação gratuita da duração inteira de cada intervalo host entre REMAP_BEGIN e REMAP_END do destino escolhido, mantendo fixos todos os custos exteriores e os 47 tokens. Para o primeiro conteúdo final, o limite termina na call 46, que produziu a amostra 45; para o decode conta as calls 3 a 48, as 46 avaliações depois da primeira amostra. A marca de receção do delta vem do cliente e confirma o corte causal. O denominador de 6 tok/s é **47**. O código do servidor regista o início do decode junto da primeira amostra e atualiza o fim quando tem a última, antes da resposta terminal. Estes instantes de amostragem não têm uma linha própria no PFJ. Todas as callbacks das calls 3–48 ficam dentro do relógio de decode pela ordem do servidor com uma slot e os 46 IDs confirmados de alimento. [Critério congelado](protocol.md) · [Definição do relógio do servidor](../../../../../../packed_nvme_manifest/server_profile/conversation/relogios.md) · [Corte HTTP](../client_cut.md)

A atribuição vem das 36 colocações no stderr autenticado do próprio PID e da reserva efetivamente impressa, verificada por bytes. Os três pesos de cada camada ocupam 40 × 3 × 4 406 400 B. As camadas 0–24 totalizam 12 606,81 MiB no buffer CPU e as 25–35 totalizam 5 547,00 MiB em CUDA0. O leitor confere a camada adicional de output e exclui-a dos experts. Os dois pins partilham a fonte llama-model.cpp com SHA-256 7af9ef3b…8f010. A lista da CPU admite buffers do host e o seu buffer CPU normal. O caminho de criação dos experts escolhe os buffers suportados para MUL_MAT_ID a partir da lista da camada. O gestor imprime o tamanho realmente alocado por tipo de buffer. Com apenas os dois pools observados, um fallback de pesos de CUDA0 para CPU reduziria o agregado CUDA0 por pelo menos uma matriz de 40 slots. O ajustamento da apresentação dos MiB a duas casas é inferior a 0,005 MiB. [Regra anterior de colocação](../../../../layer_budget.py) · [Verificador e pins](score.py)

A atribuição é ao destino dos pesos servidos durante a callback. A chamada corre na thread host zero, e o intervalo inclui reservas, espera, escrita de IDs e o custo de observação no próprio braço. O primeiro marcador vem depois da obtenção do mutex e o último precede o retorno. O tempo de entrada no mutex, o dispatch do grafo e o último leitor da GPU ficam fora desta atribuição. Eliminar a união observada constitui um limite condicional para a intervenção definida. [Hooks C291](../../observer.patch)


## Proveniência e reprodução

O pré-registo é `155b7294`, o revisor das uniões `4f76e4f3` e a ligação à família física `124a4337`. A referência C269 foi reproduzida duas vezes, recibo `0dbc813effc4546732d7a7254fc3ccf94e13c8682c2e6c552b99591ce6bfdcc4`. Para P, a primeira execução usou os originais da família e a segunda reabriu as cópias verificadas da parte 97, manifesto `a649b2e520fcbcc9c8897e4465f85fa6bb38504ab11a5189e71ded47a2ba9309`. Os dois resultados são byte a byte iguais, SHA-256 `44a00a0660c4430156ad0e705abee364c4c6cbeb608f4da08dc14c15a35c9277`. Esta análise de CPU não fez forwards, nem acedeu a pesos. Os testes cobrem adulteração dos inputs HTTP, colocação incompatível, corte em movimento e a proibição de contar duas vezes um intervalo de ambos os relógios.

```sh
python3 -IB score.py --arm C269 --arm-dir "$C269_ON" --backend "$C269_SOURCE" --new-output-dir "$NEW_REF"
python3 -IB score.py --arm P --backend "$C291_SOURCE" --family "$FAMILY" \
  --family-sha256 "$FAMILY_SHA" --result-sha256 "$T2_RESULT_SHA" --http-sha256 "$T2_HTTP_SHA" \
  --new-output-dir "$NEW_PACK"
python3 -IB -m unittest discover -s .
```
