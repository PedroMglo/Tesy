# O que é possível preparar depois de T1

**NO_GO para antecipar uma tile inteira da chamada de 148 antes da próxima mensagem**, conservando a geometria de R0 nesta conversa. A história real de T1 e o template permitiram reproduzir os 12 933 bytes e os 2 197 IDs oficiais de T2. Três conteúdos alternativos válidos do próximo utilizador divergiram ao fim do mesmo prefixo de 2 052 IDs. O servidor já reutilizou 2 044. Restam **no máximo oito** posições contíguas novas antes de encontrar uma que depende da mensagem. O teste estabelece um teto. Garantir essas oito posições para todas as mensagens exigiria outra prova.

O diário DEBUG da conversa contém os dois snapshots de KV imediatamente antes das chamadas, com pos_max 2043 e 2048. Entre a admissão da mesma tarefa no slot 0 e a sua primeira amostra houve dois despachos sem retry, ambos no offset zero. Com a contagem autenticada de 2 197 posições, a geometria externa **5+148** fica reproduzida nesse braço. A capacidade anunciada de 256 no log é o limite do batch. A decomposição interna 32+32+32+32+20 nesta comparação provém do protocolo de R0. Depois das cinco posições da primeira chamada, sobram no máximo três para a seguinte. Antecipar só a chamada de cinco continua uma hipótese, com custo de preparar, cancelar ou repor KV, slots e saída para o decode. Esta experiência não mede segundos poupados.

O processo partiu da revisão f51a775d, sob scope de 512 MiB, swap desativado e 60 s. Demorou 1,94 s com 359 408 KiB de pico de RSS reportado por time. Foi usada apenas a cópia do vocabulário sem tensores e o renderer/tokenizador C269. Os textos privados e os IDs ficaram no portátil. [Protocolo](protocol.md) · [Código](screen.py) · [Recibo integral sem texto](attempt-01/receipt.json) · [Arquivo privado e manifesto](attempt-01/archive.json)

Para reproduzir, indicar a captura natural verificada, o diretório do vocabulário sem tensores, o do renderer C269 e uma saída inexistente.

```sh
python3 -IB research/qualification-retake/predictable_turn/screen.py \
  --capture "$TESY_C281_CAPTURE" --vocab-dir "$TESY_VOCAB_ONLY" \
  --renderer-dir "$TESY_C269_RENDER" --new-output-dir "$TESY_NEW_OUTPUT"
```

Na revisão de literatura de 25 de novembro de 2026, *Intent-Aware Caching* estuda a retenção de KV de pedidos já processados, incluindo o efeito do intervalo até ao turno seguinte sobre a evicção. Aqui, o prefixo de T1 está residente. A variável que se testa é quanto texto novo se pode processar antes de conhecer o conteúdo de T2 com a mesma aritmética. O ganho em cache hit rate de uma população de sessões mede outra grandeza. [Ibn Arif et al., método e avaliação §4–5](https://arxiv.org/html/2611.09715v1)
