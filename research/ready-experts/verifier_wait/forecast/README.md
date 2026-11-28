# Quanto ganhamos ao prever os experts de um token já confirmado?

**Composição com o prefill.** O ensaio físico das 726 aquisições obrigatórias poupa cerca de 660 ms aos dois controlos de leitura. A combinação ideal com o sinal por ID deixa 9,926–10,230 s no cliente. [Decisão e prazo para uma agenda finita](retention/io-result.md)

**Decisão após o ensaio físico.** A combinação testada no NVMe interno perdeu para a procura simples nos dois pares. Pediu 35,197 GB contra 10,419 GB. Só o trabalho de leitura até à primeira peça já demorou 11,714–11,896 s. O sinal do ID confirmado conserva interesse para uma intervenção com menos desperdício. [Medição física por braço](io/README.md)

**NO_GO para as duas regras a 1/2 no turno nominal.** A identificação pelo ID do token tem valor mesmo depois de retirar os experts residentes. Com o banco secundário ativo e orçamentos iguais, o ID anteciparia 215 faltas em 474 pedidos. Uma regra de popularidade geral anteciparia nove. O custo do prefill de 4,104–4,197 s é simulado e o cálculo residente é o medido no 120B. O resultado continua acima dos 10 s até ao primeiro conteúdo. [Protocolo](protocol.md) · [Dois journals, dois W, duas repetições](evidence-20261128-r01/receipt.json)

| Regra a 4,5 GB/s | Pedidos emitidos / úteis no decode | Primeiro final P97 | Primeiro final P106 | Decode de 47 IDs |
|---|---:|---:|---:|---:|
| Desligada, banco ativo | 0 / 0 | 11,433–11,662 s | 11,541–11,770 s | 7,529–7,608 s |
| ID confirmado a 1/2 | 474 / 215 | 10,386–10,611 s | 10,488–10,713 s | 6,475–6,544 s |
| Popularidade com o mesmo número de pedidos | 474 / 9 | 11,455–11,684 s | 11,556–11,785 s | 7,551–7,623 s |
| Informação de L−2 a 1/2 | 21 / 7 | 11,430–11,659 s | 11,538–11,768 s | 7,526–7,605 s |
| Acertos perfeitos entre os quatro candidatos do ID | 317 / 317 | 9,737–9,966 s | 9,861–10,091 s | 5,772–5,860 s |
| Acertos perfeitos entre os quatro candidatos de L−2 | 402 / 402 | 9,374–9,604 s | 9,484–9,713 s | 5,433–5,512 s |

Houve 788 faltas no NVMe em 1 091 reservas. As 303 restantes foram servidas pelo banco. A regra por ID acrescentaria 259 leituras sem consumidor e elevaria o volume alinhado de 10 418 847 744 B para 13 843 316 736 B. A antecipação útil até à primeira peça foi de 214 faltas em 467 emissões, contra nove em 467 na ablação. O custo usa o máximo entre o prazo do dispositivo e o do cálculo mais o serviço residual em cada passo. Inclui as três cópias e pode subestimar a demora que quatro buffers causariam. As contagens medem a reprodução das decisões de uma política. Os segundos e bytes desta intervenção são derivados do trace.

O treino do primeiro turno selou 74 278 ranks de quatro experts em 2 120 posições. Antes do decode acresceram 5 356 ranks dos 153 tokens já aceites no prefill. O seletor só aprendeu cada um dos 46 novos passos depois do seu retorno. O S físico conferiu as 1 656 uniões e as contagens de cada chamada. Em ambos os journals, desligar a previsão reproduziu todos os relógios do controlo ao nanossegundo. O oráculo por ID obteve os mesmos acertos mesmo com acesso a todo o suporte positivo desse ID. O oráculo de L−2 admitiu todas as combinações ao conceder seleção perfeita e leitura já pronta. O modelo e o código permanecem os do target. [Prova do controlo](../service.md) · [Composição das duas fontes](joint-protocol.md)

## Quanto pode ganhar qualquer limiar da combinação?

Os quatro melhores candidatos de L−2 têm 4 595 intervalos de decisão distintos nos 4 000 002 limiares inteiros. Para cada um, a avaliação conta uma só leitura quando o mesmo expert foi previsto pelas duas fontes. Mesmo a escolha do limiar com conhecimento do resultado falha a 4,5 GB/s. A 8 GB/s há uma faixa que passaria em alguns braços, com a sobreposição concedida. [Protocolo antes da procura](joint-protocol.md) · [Todas as margens, limites e empates](evidence-joint-20261128-r01/receipt.json)

| Banda admitida | Melhor margem em algum braço, extremo favorável | Melhor margem exigindo todos os braços, extremo conservador | Limiares que passam em algum braço |
|---|---:|---:|---|
| 4,5 GB/s | −167,902 ms | −480,511 ms | Nenhum |
| 8 GB/s | +279,976 ms | −22,962 ms | 293 651 a 673 780 |

A medição física adotou o limiar 383 144 escolhido com futuro a 8 GB/s. Mesmo esse cenário favorável escolheu 2 226 previsões para 352 faltas úteis e 1 874 erros. O controlo causal por ID à entrada e sem L−2 tem uma redução projetada de cerca de um segundo em relação à entrega bloqueante. Para que a combinação com o prefill atinja 10 s, ainda teria de retirar 0,386 s no extremo mais permissivo ou 0,713 s para cobrir também o mais exigente. O custo integrado desta regra e o efeito noutro histórico ficam em aberto. [Limite individual](evidence-20261128-r01/receipt.json) · [Confronto do limiar conjunto com o NVMe](io/README.md)
