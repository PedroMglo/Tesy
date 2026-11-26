# Preparação da comparação independente C133

**Preparação REPRODUZIDA. Comparação NOT_RUN_PAIR_REQUIRED.** O manifesto revalida os envelopes históricos, os hashes oficiais das duas entradas, os payloads canónicos de mensagens e os limites de cache. O primeiro turno concluiu naturalmente com 341 tokens, o segundo com 452. Para o mesmo input e a mesma referência de produto, continua por medir se uma execução independente também falha o segundo turno. O identificador canónico do conjunto de entradas é `0a96782a6be10028f4d91bbbd5d0f1efafe7327e6364281645fe0e7db5795b9f`. O recibo publicado tem SHA-256 `a3d8a270ed7d290abc581c1b54ff983a5b599d7765fd525e9b65c26c424bf570`. [Congelamento prospetivo](two_turn_protocol.md) · [Manifesto sanitizado](two_turn_evidence_r1/manifest.json)

A preparação lê apenas os originais C133 e não cria transcrições. Na primeira tentativa o manifesto foi escrito e a conversão do código de saída falhou no caminho sem par. O primeiro artefacto ficou preservado localmente. A repetição, com a conversão corrigida e num destino novo, terminou com código zero e produziu um manifesto idêntico byte a byte. Os ficheiros de capturas futuras permanecem privados; a CI pode executar a fixture sem raws e sem modelo.

```sh
python3 -B research/qualification-retake/two_turn_pair.py \
  --historical-results "$TESY_HISTORY_RESULTS" --new-output-dir "$TESY_NEW_PREP"
python3 -B -m unittest discover -s research/qualification-retake -p test_two_turn_pair.py
```

## Contrato dos objetos privados do par

O preparador e verificador funciona offline. A integração no coletor físico deverá conservar os payloads HTTP realmente enviados e as identidades medidas no lançamento. As capturas de teste sintéticas exercitam falhas do verificador. Sem capturas reais de ambos os braços, este fluxo termina na preparação. As fontes, builds e independência dos hooks do braço stock requerem revisão no congelamento da campanha. Um SHA-256 por si só não data uma observação.

1. Antes da execução, criar um `protocol.json` distinto por braço. Incluir `engine` (`Tesy-R0` ou `stock-llama.cpp`), `policy` igual ao objeto do manifesto e `identity` com `model_sha256`, `binary_sha256`, `backend_tree` Git e `library_manifest_sha256`. O último é o SHA-256 do JSON canónico do mapa de caminhos e digests das bibliotecas efetivas. Congelar e rever também a admissão física, os modelos, builds, tokenizer/template, recursos e condições de paragem nos dois protocolos. O verificador compara as identidades e os campos necessários ao emparelhamento.
2. Em `pair.json`, fixar `schema` igual a `tesy-two-turn-pair-v1`, `mode` igual a `natural` ou `fixed`, `input_sha256` igual ao identificador canónico acima e `arms` como o mapa de `r0` e `reference` para os SHA-256 dos bytes dos respetivos protocolos. Publicar a proveniência e o digest exato de `pair.json` antes de recolher as respostas.
3. Cada subdiretório privado `r0/` e `reference/` contém `protocol.json`, `raw.json`, `requests.json`, `tokenization.json` e `receipt.json`. Os dois mapas de pedidos e tokenização usam as chaves oficiais `c133-turn01` e `c133-turn02` nessa ordem. O primeiro contém o corpo HTTP completo tal como foi enviado, com o ID do modelo local, política de stream/uso, seed, temperatura, cap, cache e argumentos do template. O segundo contém arrays oficiais completos. Usar o template aplicado pelo target e a tokenização oficial com `add_special=false` e `parse_special=true`. [Payload e tokenização C2](../../tools/c2_server_run.py)
4. O raw usa `returncode`, `stop_reasons`, `launch_identity`, `preflight` e duas linhas `results` do formato C2. Preservar `id`, `source_task_id`, `started_s`, `ended_s`, `finish_reason`, `message`, `usage`, `timings` e `stream_metrics`. O preflight inclui `protocol_sha256`, `protocol`, `run_id`, `server_model_id`, `model_sha256_prior_verified`, `config.n_ctx`, `launch_identity` com PID/start ticks e `actually_loaded_backend_libraries_sha256`. O coletor acrescentará `binary_sha256`, `backend_tree` e `parallel_slots` observados. Em replay fixo, registar também o procedimento de reconstituição do prefixo no protocolo. Conservar o diário de pedidos e a evidência original do servidor para revisão.
5. O recibo de cada braço tem `schema` igual a `tesy-two-turn-capture-v1`, `model_launch_observed`, `run_id`, `pair_sha256`, `protocol_sha256`, `raw_sha256`, `requests_sha256` e `tokenization_sha256`. Os digests dos ficheiros representam bytes exatos. O digest de objetos canónicos usa `c2_server_run.digest` (JSON ordenado com separadores compactos). O verificador exige IDs, payloads e split de cache históricos para devolver um diagnóstico emparelhado. Publica apenas identidades, hashes, contagens e resultados do validador. [Fixture dos oito casos](test_two_turn_pair.py)

```sh
python3 -B research/qualification-retake/two_turn_pair.py \
  --historical-results "$TESY_HISTORY_RESULTS" --new-output-dir "$TESY_NEW_COMPARISON" \
  --pair-dir "$TESY_PRIVATE_PAIR" --pair-sha256 "$TESY_PREFROZEN_PAIR_SHA"
```

No modo explícito de comparação, um braço ausente produz `NOT_RUN_PAIR_REQUIRED` e código diferente de zero. Um envelope incompleto, um protocolo alterado ou um turno truncado produz `FAIL_EVIDENCE`. Uma mudança de IDs, payload histórico ou split de cache, com envelopes internamente válidos, produz `INCONCLUSIVE`. Um par válido fica `DIAGNOSTICO_PAIRED`, com a nota de cada braço. O verificador não mede logits, recursos físicos, causalidade ou M4.
