# O tamanho de procura e o comprimento que o servidor aceita

**REPRODUZIDO.** No servidor pinado, configurar a procura para três tokens e limitar a proposta a dois produz zero propostas. O helper exige que a continuação tenha pelo menos o comprimento da procura e limita-a em simultâneo a M. Com N=3 e M=2, a primeira condição nunca se cumpre. O dispatcher confirmou 77 passos seriais em T1 e 46 em T2. A biblioteca opt-in do Tesy verifica o token anterior da ocorrência mais recente de um bigrama e conserva a proposta máxima de dois. [Patch isolado](previous-token.patch) · [Protocolo](protocol.md)

| Dispatcher | T1 · blocos e aceitações 0 / 1 / 2 | T2 · blocos e aceitações 0 / 1 / 2 |
|---|---|---|
| N2/M2 instalado e biblioteca nova, filtro OFF | 9 · 2 / 3 / 4 | 11 · 5 / 0 / 6 |
| N3/M2 instalado | 0 | 0 |
| N2/M2 com filtro ON | 7 · 3 / 0 / 4 | 7 · 1 / 3 / 3 |

O objeto e a biblioteca comum do controlo recompilaram byte a byte. Os braços do filtro usam o mesmo ELF. O dispatcher e o helper direto coincidiram em cada posição, e a verificação de cada proposta conservou os 78 e 47 IDs reais, incluindo EOG. O cap e a ocorrência mais recente discordante foram exercitados em fixtures separadas. O resultado N2 de origem reproduziu todos os bytes da parte 177. A novidade desta etapa é executar a regra já projetada na parte 186 dentro da biblioteca que alimenta o servidor. **GO apenas para a integração diagnóstica.** As cinco verificações de preço ainda desconhecido são as de T2 com 11, 16, 19, 37 e 41 tokens já confirmados. [Resultado por braço e por posição](result.json) · [Conta condicional anterior](../context.md)

Primeiro build interrompido ao aplicar um hunk incorreto, antes de iniciar o dispatcher. O diff corrigido compilou duas vezes no commit `3fe72bc486a5ddb945197e841e679fdcce9cc3ac`. As bibliotecas de controlo e candidata têm SHA-256 `cc5a0f0b264bdd093287cfdb38f3607b8ab98bd35ae21f4550ddc44076c92d27` e `c4644477420b8d41d46db8d26291a4c4604afb70aa5c7dd415a3aa3412717914`. Os processos com êxito duraram 5,00 e 5,09 s, com picos de 358,3 e 354,4 MiB no cgroup, zero swap, forwards ou pedidos HTTP. A parte 192 guarda os três builds e as propostas privadas em 96 ficheiros, 31 240 173 B. A revisão sobre originais e arquivo produziu `6882001e2807aa25ddc92b94829b696f3f5b77be373803f01d677421fe57c1ff`. [Diagnóstico de R01](r02.md) · [Recibo do arquivo](../../../../../../../../../../../../private_archive/part-192.json)

```sh
python3 -IB "$STUDY/review.py" --failed "$R01" --first "$R02" --second "$R03" --new-output-dir "$NEW"
```
