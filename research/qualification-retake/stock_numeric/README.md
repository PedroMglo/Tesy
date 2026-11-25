# Comparação C110 com o cache stock E10

O [protocolo](protocol.md) fixa a pergunta, a diferença entre os dois backends, os IDs fornecidos e a decisão antes dos logits candidatos. O único executável disponível no build pinado é `llama-server`. Os seus campos HTTP de probabilidades transformam ou selecionam logits. O [cliente C++](client.cpp) liga diretamente às bibliotecas stock existentes e obtém os 201 088 valores float32 por posição com `llama_get_logits_ith`. Antes dos dados de ensaio invoca a mesma sonda interna de dois IDs zero que o servidor executa para a remoção parcial de sequência; verifica o KV vazio à saída. A sonda pode deixar os bancos de experts povoados. [API para a linha de logits](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/include/llama.h#L1137-L1149) · [Sonda stock](../stock_log/README.md)

**Preparação sem modelo.** Os seis raws históricos A/B/C de C109 e C110 coincidiram com os seus manifestos e entre si. A fixture TSV original contém 2009 IDs de prompt e 192 de continuação. A representação privada exata dos 16+2 selecionados tem 72 B, SHA-256 `80536eadb97029b88c1d54a06a0ffb2f693c2a10029631f10e59e86745d73479`. O [avaliador](evaluate.py) reutiliza o teste de três linhas completas, distingue bytes diferentes com o mesmo argmax (incluindo ±0) e conta NaN/±infinito. [Recibo das seis referências](reference-r1/receipt.json)

O primeiro build parou antes de produzir binário porque o tipo de ponteiro para `fclose` tinha atributos ignorados com warnings tratados como erros. Mantendo o mesmo compilador e opções, um deleter explícito corrigiu o problema. O build seguinte durou 1,214 s com pico de 254 520 KiB do filho. O novo executável SHA-256 `07b6572b967a7517340b6e3a67e0fea1b8b9cd6d1294ae6f5e55d27ac984eb43` resolveu os seis DSOs stock esperados. Testes do executável aceitaram a fixture exata e rejeitaram entrada truncada, excedente e ID fora do vocabulário antes de tocar no modelo. [Build preservado](build-r1/receipt.json) · [Build qualificado](build-r2/receipt.json)

```sh
python3 research/qualification-retake/stock_numeric/test_numeric.py
python3 research/qualification-retake/stock_numeric/evaluate.py \
  --raw-parent "$C110_RESULTS" --new-output "$NEW_REFERENCE_DIR"
python3 research/qualification-retake/stock_numeric/prepare.py \
  --stock "$STOCK_WORKSPACE" --stock-receipt "$STOCK_BUILD_RECEIPT" \
  --raw-parent "$C110_RESULTS" --new-private "$NEW_BUILD" --new-output "$NEW_BUILD_RECEIPT"
```

O [supervisor físico](run.py) exige C55 válido, scope E10 FILE_PAGING com high de 9,5 GiB e swap zero, a cópia NVMe verificada, o cliente e os DSOs por hash, os seis vetores independentes e C118 fresco. Entrega os 72 B já verificados ao stdin do cliente. O modo `--before-inventory-only` encerra antes de criar o filho de modelo. Os resultados numéricos dependem de uma execução com identidade exclusiva e aprovação do coordenador.
