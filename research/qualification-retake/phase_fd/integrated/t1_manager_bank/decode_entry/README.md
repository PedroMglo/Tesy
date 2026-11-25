# Tabela primária na entrada do primeiro decode

**REPRODUZIDO, referência offline para 1 440 descritores.** Nas duas conversas nominais C281 ON, cada uma das 36 camadas chegou ao primeiro decode com os mesmos 40 experts READY, na mesma posição física e com o mesmo número de geração por slot. Em todas as camadas, ambos os braços tinham zero EMPTY, LOADING e claims, FIFO vazia e nenhum trabalho de carregamento ativo. A comparação por camada consta do recibo. Estes resultados permitem testar a reposição dos vínculos num controlo contemporâneo. [Protocolo congelado em 341f8ea2](protocol.md) · [Recibo](receipt.json)

| Do início de T2 até ao ENTER de decode | ON T2 | ON sufixo T1 + T2 | Comparação |
|---|---:|---:|---|
| Linhas de ranks top-4 | 5 356 | 5 356 | Mesmas linhas e ordem |
| DEMAND com camada, expert, slot e geração | 3 826 | 3 826 | Mesmas identidades e ordem |
| Reservas | 1 263 | 1 263 | Mesmas identidades e ordem |
| Publicações | 1 263 | 1 263 | Mesmas identidades em ordem diferente |
| Intervalo do RETURN de 148 até ao ENTER | 3,383422 ms | 3,408971 ms | Cada valor no relógio do próprio PFJ1 |

Os dois prefixos processaram as posições 2044–2048 e 2049–2196, com a geometria 5 e 32+32+32+32+20. O corte ocorre sob o mutex na entrada da posição 2197, antes da primeira procura de decode. O RETURN anterior já declarou zero claims e zero itens de fila. Entre os dois marcadores não ocorreu qualquer evento PFJ1. O segundo processo tinha 73 chamadas de T1 no início do journal. Ambos os journals selados passaram a sua conservação completa. A diferença de ordem e multiplicidade no comparador integral anterior conserva o seu FAIL. [Instrumentação](../../phase-fd-integrated.h) · [Diagnóstico anterior](../../t1_local/README.md)

**Limites da reposição.** O replay usou as reservas e publicações efetivamente escolhidas pelo R0. A repetição dos descritores neste par deixa por provar que um candidato com outra política consiga determinar a tabela apenas com a informação disponível online ou que baste restaurá-la para manter as decisões futuras. A fixture pode usar a tabela como oráculo e contabilizar leituras, trocas de slot e scratch. Cada nova reserva do candidato continua a avançar a sua própria geração. Repor números antigos numa estrutura com referências em voo poderia revalidar uma conclusão obsoleta. [Plano do pedido inteiro](../pedido-integral.md)

Parking designa o uso de slots residentes por ranks mascarados de uma wave. O C269 compõe o pool com slots de procura e eventuais empréstimos da wave anterior, depois emite os IDs remapeados por token. O estado do slot continua READY. O PFJ1 observa a lista de procura da wave e os ranks originais. Omite o pool completo, os IDs físicos efetivamente emitidos por rank mascarado e os valores iniciais dos contadores de frequência e idade. Para verificar parking bastam os IDs pós-remapeamento e as máscaras nos limites da fixture. Para testar a mesma política de vítima após a reposição, comparar as próximas reservas com R0 ou observar também o estado dos contadores sob o mutex. Comparar separadamente as vistas KV e os logits completos do primeiro decode. O estado numérico e o efeito de produto continuam **INCONCLUSIVE**. [Código e arestas no pin C269](../cuda-consumers.md)

O verificador usa a biblioteca padrão, autentica os dois manifestos, recibos e PFJ1 e lê zero bytes do modelo. As duas execuções finais geraram o mesmo SHA-256 `def18d5ad7e20a7c47033e690ed8da64c3ff6066879b97db5ebadf3fc8f680e2` em 0,51 s cada e até 72 744 KiB de RSS. As verificações portáteis cobrem troca física com membros iguais, geração diferente, claims herdados sem identidade de worker, FIFO com duplicados e trabalhos em voo.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_bank/decode_entry
python3 -IB "$unit/test_compare.py"
python3 -IB "$unit/compare.py" --archive-root "$ARCHIVE" --new-output-dir "$NEW"
cmp "$NEW/receipt.json" "$unit/receipt.json"
```
