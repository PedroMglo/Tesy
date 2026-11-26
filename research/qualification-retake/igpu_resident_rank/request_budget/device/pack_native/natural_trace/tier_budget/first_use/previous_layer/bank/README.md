# O banco acrescenta 52,875 ms à antecipação de uma camada

**A combinação melhora o limite dos dois métodos isolados. Ainda ficam a faltar 18,519 ms para atingir 10 s** no cenário mais favorável do banco histórico: 8 GB/s, pesos parcialmente antecipáveis e preditor perfeito da camada seguinte. O piso para servir as 375 primeiras procuras CPU desce de 619,650 para 109,161 ms. A margem disponível no P é 90,641 ms, o que põe o primeiro conteúdo final em **pelo menos 10,018519 s**. NO_GO para esses dois mecanismos, com a seleção fixa da parte 63 e o restante trabalho conservado. [Custos por braço](receipt.json) · [Incidência nas 110 callbacks](windows.tsv)

| Serviço residual das 375 primeiras procuras (ms) | Nenhuma intervenção | Últimas 353 vítimas | Antecipação por uma camada | Os dois mecanismos | Margem conjunta até 10 s |
|---|---:|---:|---:|---:|---:|
| 8 GB/s, expert parcial | 619,650 | 512,244 | 162,036 | 109,161 | −18,519 |
| 8 GB/s, só experts inteiros antecipados | 619,650 | 512,244 | 196,636 | 133,844 | −43,203 |
| 4,5 GB/s, expert parcial | 1 101,600 | 910,656 | 501,703 | 367,556 | −276,914 |
| 4,5 GB/s, só experts inteiros antecipados | 1 101,600 | 910,656 | 581,645 | 440,640 | −349,999 |

A 8 GB/s, retirar isoladamente os 65 experts do disco pouparia 107,406 ms. Em cada janela o revisor retira os acertos do banco antes de aplicar a banda à procura que resta. O banco acrescenta então **52,875 ms** à antecipação de pesos parciais. Somar os ganhos isolados contaria **54,531 ms** de trabalho duas vezes. Esse ganho marginal é o orçamento para que o banco melhore o braço com preditor se os preços forem realizáveis. O objetivo de 10 s continua fora do alcance mesmo com o banco gratuito. A 4,5 GB/s a contribuição marginal correspondente é 134,147 ms. [Antecipação isolada](../README.md) · [Seleção antes do segundo pedido](../../last353.md)

## Que seleção poderia mudar o resultado?

O sufixo observado de T1 na parte 63 ofereceu 236 das 375 chaves CPU como vítimas READY. O teto concede retenção e acerto nas 236. Mesmo custando zero, a 4,5 GB/s ainda sobram 104,214 ms de serviço parcial, **13,572 ms além da margem**. A 8 GB/s esse custo desce para 31,266 ms, deixando **59,375617 ms no máximo** para todos os custos adicionais que atrasem o primeiro final de T2. Exigindo experts inteiros na antecipação, o teto passa a 50,983739 ms. Isso apenas abre a pergunta de seleção causal. T1 de P não tem a sua própria sequência de ofertas observada. As identidades das ofertas e do banco vêm da parte 63. As duas execuções coincidem nos 1 440 slots à entrada de T2 e nos 7 012 quartetos ordenados da rota. Os tempos usados pertencem ao P.

Para fechar o défice de 18,519 ms seria necessário substituir pelo menos **12 escolhas** por outras vítimas do sufixo, em janelas com serviço restante e a 8 GB/s. As 11 melhores só retiram 18,1764 ms. As 12 melhores retiram 19,8288 ms e deixam apenas **1,309571 ms** para os custos acrescidos em T2. No modelo de experts inteiros o mínimo sobe para **27 escolhas**, com 1,411739 ms de folga. A conta ordena os créditos marginais da próxima chave elegível em cada sítio. Não prova que um seletor saiba essas chaves em T1 nem que retirar as vítimas originalmente escolhidas preserve as restantes fases.

## Em que turno se pagam as cópias?

- **T1.** Formar last353 a partir de vazio nesse sufixo, por cópias de vítimas, implicava 1 530 capturas CPU (20 225 376 000 B) e 613 CUDA (8 103 369 600 B). O conteúdo útil que sobrevive tinha 4 666 377 600 B, 263 entradas CPU e 90 CUDA. Esses bytes pertencem à preparação do primeiro turno. O journal de P não mede a latência dessa política. [Aquisição e residência](../../../../../../../../../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/replay/README.md)
- **T2.** Se o banco materializado repuser estas 65 chaves por cópia ao primário, o payload correspondente é 859 248 000 B. Para as 236 do teto são 3 119 731 200 B. Quanto do transporte, da validação de geração e do SET fica exposto ao cliente depende da implementação. A fixture real do manager confirmou recuperação de três entradas CPU, com as publicações e os SET preservados. [Fixture de captura e reposição](../../../../../../../../../phase_fd/integrated/t1_manager_bank/README.md)
- **Entrada em decode.** Alterar também a escolha da vítima na parte 63 deslocava 447 vínculos. Para reconstituir R0, esse outro braço precisava de 19 admissões do banco e de 306 movimentos CPU mais 122 CUDA, com 5 657 817 600 B úteis nos movimentos. Esse preço é específico da alteração da agenda. Preservar os mesmos slots e gerações do P é uma premissa do presente crivo. [Restauro dessa variante](../../../../../../../../../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/replay/README.md)

O protocolo secundário foi congelado em `8be6d5d7`. As duas reproduções em processos distintos (1,20/1,25 s, 87 096/86 916 KiB RSS) reabriram o original e a cópia arquivada do P, sem pesos nem modelo. Geraram o recibo `ba53f8bf1f863204ee95053e4f35ac50f048455b58071fbdfc024d8215f048ac` e a tabela `057489755230037e778a9ea5c795ea038ae75090950dbcaac4d38dece79a759f`. Três testes incluem acertos já totalmente escondidos na mesma janela, crédito parcial, custos inteiros e substituições elegíveis. [Protocolo](protocol.md) · [Verificador](score.py)

```sh
python3 -IB -m unittest discover -s "$STUDY"
timeout 60 prlimit --as=536870912 -- python3 -IB "$STUDY/score.py" \
  --part63 "$ARCHIVE/part-63" --family "$FAMILY_P" --backend "$C291_SOURCE" \
  --new-output-dir "$NEW"
```
