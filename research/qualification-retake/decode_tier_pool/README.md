# Partilhar a cache entre camadas apenas durante o decode

**NO_GO para LRU por tier a partir do estado I do R0.** A política partilhada precisou de 1 271 admissões no nominal e 1 465 em código, contando a reposição dos experts do estado final F. O R0 físico precisou de 1 081 e 1 308. A ablação com a mesma recência e bancos locais precisou de 1 192 e 1 391. As repetições 2 e 3 de cada caso coincidiram em todas as contagens por camada. Mesmo oferecendo gratuitamente a partilha das vistas e a normalização das posições finais, falham os quatro braços. [Pré-registo](protocol.md) · [Recibo por braço e por tier](evidence/receipt.json)

| Braços C294 trace-ON | Política | Hits | Admissões CPU + CUDA | Reposição de F CPU + CUDA | Total cobrado | Grupos com falta / 1 152 | Residentes fora do lugar em F |
|---|---|---:|---:|---:|---:|---:|---:|
| Nominal 2 e 3 | R0 | 3 527 | 762 + 319 | 0 | 1 081 | 683 | 0 |
| Nominal 2 e 3 | LRU local | 3 504 | 774 + 330 | 67 + 21 | 1 192 | 701 | 896 |
| Nominal 2 e 3 | LRU por tier | 3 443 | 844 + 321 | 82 + 24 | 1 271 | 712 | 1 026 |
| Código 2 e 3 | R0 | 3 300 | 927 + 381 | 0 | 1 308 | 819 | 0 |
| Código 2 e 3 | LRU local | 3 319 | 923 + 366 | 77 + 25 | 1 391 | 802 | 1 010 |
| Código 2 e 3 | LRU por tier | 3 281 | 957 + 370 | 100 + 38 | 1 465 | 818 | 1 117 |

O gate de 15% permitia no nominal até 918 admissões contra R0 e 1 013 contra a ablação. O candidato excedeu-os em 353 e 258. Em código, os limites eram 1 111 e 1 182 e os excessos 354 e 283. No nominal, a partilha eliminou faltas em 34 grupos antes afetados no R0 e introduziu faltas em 63 grupos antes totalmente residentes. Em código, eliminou-as em 32 grupos e introduziu-as em 31, embora as admissões de procura subissem de 1 308 para 1 327. Uma contagem de grupos não determina a duração do passo. [Regra de decisão e contagens](screen.py)

O replay **TRACE_DERIVED** começa depois do prefixo P e do incremento, no I drenado e autenticado de cada braço. Conserva os 1 000 lugares CPU e os 440 CUDA, as 4 608 escolhas de rank e quatro pins por grupo. As duas políticas têm o mesmo desempate físico e iniciam a idade de todos os residentes a zero. O restauro conta cargas de identidades ausentes. Um expert de F já residente num lugar diferente exige uma mudança de mapeamento ou cópia no seu próprio dispositivo. Se fosse copiado por inteiro, o payload lógico dessas posições seria de 13 562 899 200 B no nominal e 14 765 846 400 B em código para LRU por tier. O teste concede todo esse trabalho gratuitamente. Um algoritmo clássico de permutação pode executar um ciclo com um slot temporário de 13 219 200 B no tier em causa. Se todos os slots estiverem ocupados, usá-lo requer memória adicional ou uma vaga demonstrada. Poder-se-ia trabalhar em fragmentos com outra coordenação. Nenhuma destas estratégias foi implementada. Também ficam por provar os metadados, as gerações, o layout efetivo dos tensores e as latências. [Origem de I e F](../cache_boundary.py) · [Quotas fixas e tensores por camada](../tier_quotas/README.md)

O resultado fecha esta política e inicialização no decode. Qualquer continuação exige uma premissa nova, como uma política causal cuja seleção de vítimas justifique as admissões e a reposição em ambos os casos. O prefill continua a precisar da sua própria intervenção para o alvo de M4. M3 PARTIAL, M4 NOT_MET.

**Reprodução.** Protocolo em `708146b2`. Código medido em `a759253db1b17edf3b862c041d3aad91366d362b`, árvore limpa `b2125b627cf0ddc1fda0e083d5074a05f4a0200c`. Os dois recibos integrais têm 119 604 B e SHA-256 `5d81816e9d2d09db16d5da94b410e06130e959148cc233eacc80e9c6d726f052`. R01/R02 usaram 1,00/0,84 s de parede e 45 948/46 532 KiB de RSS máximo. Quatro testes sem modelo cobrem empates físicos, pin de rank posterior, precedência de slot vazio, identidade de camada, distinção entre deslocação e releitura, isolamento dos tiers e igualdade no limiar. Sem GPU, pesos ou forwards.

```sh
python3 -B -m unittest discover -s research/qualification-retake/decode_tier_pool
python3 -B research/qualification-retake/decode_tier_pool/screen.py \
  --raw-dir "$C7/results/c294-feature-ready-service-window-20261006/raw" \
  --new-output-dir "$NEW_OUT"
sha256sum "$NEW_OUT/receipt.json"
jq -S 'del(.arms[].policies[].layers)' "$NEW_OUT/receipt.json" | \
  cmp - research/qualification-retake/decode_tier_pool/evidence/receipt.json
```

Na confirmação original o recibo público foi acrescentado depois do commit de execução. O integral inclui as 36 linhas por camada de cada política. A projeção publicada conserva os totais dos dois tiers, as contagens por braço, a proveniência e as decisões.
