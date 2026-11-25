# Primeiros bytes de Aster no segundo turno

**REPRODUZIDO · `prefix_visible_equal`.** Os oito tokens gerados pelo stock E10 expõem 28 bytes UTF-8 estáveis no canal `reasoning_content`. Coincidem byte a byte com o início do mesmo canal na resposta natural histórica do R0 C133. Os oito tokens incluem os que identificam o canal. A janela termina no limite de geração e fica inteiramente antes do conteúdo final. A atribuição da falha funcional de Aster continua **INCONCLUSIVE**. M3 permanece PARTIAL, com 19/20 tarefas aprovadas em C133. [Recibo compacto](compact-r1/receipt.json) · [Diagnóstico físico do stock](../aster_turn2_budget/README.md)

## O que se comparou

O stock recebeu o mesmo vetor lógico de 435 IDs e mediu 122 tokens em cache e 313 novos. Um pedido fixo preparou a cache do stock. O R0 chegou ao turno 2 com o histórico natural do próprio braço. A comparação converte os IDs emitidos pelo stock em peças através da cópia GGUF autenticada do vocabulário, com zero tensores. O envelope C133 contém o texto acumulado por canal. Os IDs individuais de saída do R0, os seus logits e a sua sequência após o prefixo continuam desconhecidos para este contraste. [Contrato dos turnos](../two_turn_pair.py) · [Vocabulário](../aster_vocab/README.md)

A prova de formato cobre uma produção comum aos dois parsers. No C75 `27d2e42d`, `common/chat.cpp` associa o cabeçalho Harmony de análise à regra `reasoning(content)`, depois de acrescentar o prefixo de geração. O vetor do pedido termina nos tokens de início e de papel do assistente. O mapeador em `common/chat-peg-parser.cpp` acrescenta os bytes literais e descarta um campo de raciocínio inteiramente branco. Os deltas calculados pelo servidor em `tools/server/server-task.cpp` chegam ao cliente C133, que os concatena por canal preservando os espaços. O cliente usa `strip()` só para marcar relógios. [Leitor de C133](../../../tools/c2_server_run.py)

No stock `e95426f1`, a mesma produção aparece em `common/parsers/gpt-oss.cpp`. O mapeador aplica `sanitized_text()`, que devolve os bytes originais quando o UTF-8 é válido. O verificador exige que os delimitadores de canal e mensagem sejam tokens de controlo, reconhece o nome do canal e compara somente o segmento literal UTF-8 completo que se segue. Corpos inteiramente brancos, delimitadores parciais, controlos embutidos ou canais ambíguos dão INCONCLUSIVE. Os pins e blobs conferidos estão no verificador. Esta derivação aplica-se ao prefixo parcial observado, sem finalizar o parser por ter chegado ao oitavo token. [Verificador](screen.py) · [Fixtures de falha e de coincidência parcial](test_screen.py)

## Reprodução

As duas confirmações CPU decorreram na revisão limpa `652c9b75f2b6362bcafd5d81b8b53a2e38383360`, árvore `67e162e810d59c01ffe8e2c053f45987c04ffd8b`. R01 consumiu 0,25 s e 33 080 KiB de RSS máxima. R02 consumiu 0,18 s e 32 696 KiB. Ambas produziram o mesmo recibo de SHA-256 `1d860641acd625ad70e1cae29101b04ba420857cd7fce07fc1b3da80e13d38c0`, com zero forwards e zero uso de GPU. [Protocolo e orçamento](protocol.md)

Na checkout limpa dessa revisão, indicar o diretório de resultados históricos do C7, o diretório privado que contém `T2.sse` e `T2.request.json`, o GGUF sem tensores e o diretório pai das checkouts nativas `streaming` e `stock-e95426-sm89-20261124b/source`. Cada execução exige um destino novo.

```sh
python3 -B research/qualification-retake/aster_reasoning_prefix/screen.py \
  --historical-results "$C7/results" --stock-raw "$STOCK_T2_RAW" \
  --vocab "$VOCAB_ONLY_GGUF" --native-backends "$TESY_NATIVE_BACKENDS" \
  --new-output-dir "$NEW_OUTPUT"
```

A próxima observação discriminante para o produto é a conclusão natural validada de Aster numa referência independente, com os IDs, o histórico, o split de cache e os recursos conferidos. Para localizar uma divergência de tokens seria ainda necessária uma captura emparelhada dos IDs de saída dos dois braços. Os 28 bytes coincidentes deixam ambas as perguntas em aberto. [Contrato da referência](../product.md)
