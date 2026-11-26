# Combinar propostas de histórico com entregas de experts mais rápidas

No turno natural instrumentado, a primeira peça final chegou em 18,325561 s. Das 44 avaliações que a precederam, o proponente teria mantido 23 avaliações individuais e iniciado dez verificações. Se essas verificações e as avaliações dispensadas tivessem custo zero, retirar a duração inteira das 21 chamadas correspondentes teria adiantado a peça em **4,032374 s**. Restariam **14,293187 s**. O prefill e as 23 avaliações ordinárias tinham em conjunto **9,360731 s** dentro de callbacks de remap. Esta segunda parcela conta apenas trabalho que a primeira intervenção conservou. [Protocolo congelado](protocol.md) · [Recibo verificado](evidence.json)

| Fração retirada dos remaps conservados | Primeiro final com B3 gratuito | Decode completo com B3 gratuito | Orçamento uniforme por verificação, incluindo custos adicionais |
|---|---:|---:|---:|
| 0% | 14,293 s | 4,676 s | défice de 429,319 ms |
| 50% | 9,613 s | 2,945 s | 38,718 ms |
| 100% | 4,932 s | 1,214 s | 506,754 ms |

O quadro mantém o tempo exterior às chamadas, concede todo o tempo dos envelopes das chamadas substituídas e exige 10 s e 47/6 s nos dois relógios. A linha de 50% tem só **387,179 ms** para as dez verificações que já começaram antes da peça final e para a coordenação até esse ponto. Nas onze verificações do decode inteiro também é necessário caber no orçamento desse relógio. Dar gratuitamente todo o tempo exterior às chamadas elevaria aquele orçamento uniforme para 53,785 ms. São cenários TRACE_DERIVED. O tempo real de verificação, a exatidão dos logits e a atualização do KV continuam a exigir execução.

O mínimo de remap a eliminar com B3 gratuito seria 45,864% do tempo das callbacks conservadas. Ao cobrar os bytes das linhas conhecidas que o target ainda teria de verificar, são necessários **pelo menos 54,408% a 8 GB/s** ou **61,053% a 4,5 GB/s**, sob trânsito em série por um único recurso com esse teto, admitindo a entrega parcial no bloco que atravessa a primeira peça final. Estes limiares ainda concedem cálculo e coordenação de B3 gratuitos. O crivo inclui o preço do retorno à residência de controlo no fim de cada bloco. Os dois inputs especulativos que seguem a primeira proposta rejeitada ficam sem preço. [Piso dos 11 blocos e sensibilidades](working_set/README.md)

O protocolo precedeu o ON em bd341143. O revisor 4f76e4f3 e três fixtures distinguem os intervalos, o limite da primeira peça e os casos sem margem. Original e cópia integral da parte 97 produziram o mesmo recibo SHA-256 `f0a98bc6ca418cb1816e80c7777570a6429bd1a679757d0c43c997274025bc01`. A execução é CPU sem pesos, em destino exclusivo.

```sh
prlimit --as=536870912 --cpu=120 -- python3 -IB "$LOOKUP/screen.py" \
  --family-dir "$FAMILY" --family-sha256 e5012e559a2403145abc6f5317bddc8b83f95f1e09b592eb83a6baa2c18980a9 \
  --new-output-dir "$NEW_RESULT"
```
