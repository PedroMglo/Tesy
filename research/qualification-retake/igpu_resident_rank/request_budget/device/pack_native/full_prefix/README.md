# Corte de T1 antes da segunda pergunta

**PASS_FULL_PREFIX_NATIVE_CUT, fixture CPU sem modelo.** O cliente leu o corte publicado pelo manager C291 antes de entrar na chamada 87. Após o fecho dos quatro workers, os mesmos 1 903 registos conservavam o mesmo SHA-256. Isto permite testar se as vítimas escolhidas desde a primeira posição de T1 ajudam na pergunta seguinte. A exatidão do observador na inferência e a seleção numa conversa natural têm gates próprios. [Protocolo](protocol.md) · [Recibo compacto](evidence.json)

| Processo | Corte antes da chamada seguinte | Resultado no journal |
|---|---:|---|
| OFF | 0 | Nenhum ficheiro, mesmos slots e cinco cargas validadas |
| ON | 1 903 | 4 reservas e 4 publicações no prefixo. O sufixo contém 1 576 registos, incluindo um snapshot de 1 440 slots, uma leitura de pack, três SET, uma publicação, quatro saídas de worker e END |
| Posição final 2118 | 0 | O writer assinalou o erro, flags 5 |
| EINTR injetado | 0 | O writer assinalou a repetição, flags 5 |

Cada caso positivo verifica 66 096 000 B de matrizes provenientes de cinco registos de teste e dois grafos CPU de remap. As 85 chamadas intermédias exercitam as fronteiras sem carga adicional de experts. A enumeração dos 87 ENTER vem do PFJ. O campo legado `native_calls=1` do filho descreve a fixture de origem e não serve de censo desta extensão. O modelo, o servidor e a GPU tiveram zero lançamentos nesta medição.

A fonte do observador foi congelada em `dca6e230`, o binário da fixture em `712adbc0`. O build privado terminou em 14,759 s. A família da fixture levou 4,743 s e atingiu 392 978 432 B no cgroup de 1 GiB, com swap zero e sem eventos de OOM. O journal produtivo tem 134 217 664 B de capacidade. O limite de T1 é 1 194 324 registos e o supervisor exige ainda 262 144 lugares livres efetivos antes do segundo POST. O tamanho observado na fixture cobre a passagem de fase, não dimensiona uma conversa. [Verificador de conservação](audit.py) · [Controlo numérico](numeric) · [Sessão C281](session)

A reprodução usa os diretórios novos de resultados e dados, a compilação de C291 pinada e as bibliotecas de CPU registadas no recibo do build. Dentro do scope da fixture, na checkout limpa, executar o comando abaixo com os caminhos admitidos. Os dados de teste são esparsos e independentes dos pesos.

```sh
python3 -IB fixture.py --backend "$C291" --libs "$GGML_LIBS" \
  --build-dir "$BUILD" --build-sha256 a125301f45a1a08c2774527d59c59ef09de5f4530fe9d6f8a80335288b2a5cad \
  --scope-unit "$UNIT" --commit 712adbc0553593607d955eb7b995e80f22bc4c11 \
  --new-data-dir "$NEW_DATA" --new-output-dir "$NEW_OUTPUT"
```
