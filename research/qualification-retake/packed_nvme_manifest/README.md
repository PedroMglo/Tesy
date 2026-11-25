# Manifesto C291 para o pack integral no NVMe

**R01 passou a validação dos metadados e do construtor C291. A memória da derivação R01 ficou INCONCLUSIVE.** O índice conserva as 4 608 entradas nas 36 camadas, os 13 824 descritores de pesos e o total de 27 648 componentes, incluindo os biases. Usou a cópia integral C290 de 61 096 329 216 bytes qualificada no NVMe. A derivação leu metadados e verificou o FD dos pesos. O contador de bytes de payload lidos nesta fase foi zero. [Protocolo](protocol.md) · [Colocação integral](../packed_nvme_placement/)

| Fase R01 no commit `b809f186e7df3ee8b8b4ef1d6d1e7550d222fdbe` | Resultado | Tempo | Memória registada |
|---|---|---:|---:|
| Derivação | `PASS_DERIVED_C290_NVME_METADATA` | 0,453 s | 650 912 KiB de `ru_maxrss` |
| Construtor nativo recompilado da fonte C291 | `PASS_C291_NATIVE_CONSTRUCTOR` | 2,694 s, incluindo compilação | 24 496 KiB no supervisor e 351 220 KiB no maior filho |

Na cópia derivada do índice mudam `pack_path` e `model_stat`. O manifesto altera `model_stat`, `index_path`, `index_sha256`, `index_stat` e `pack_stat`. O índice e o manifesto contêm caminhos absolutos e o manifesto fixa o inode do índice. A reprodução produz estes artefactos num novo destino e emite digests próprios. Os recibos privados conservam os caminhos e os stats. [Programa de derivação](derive.py)

| Artefacto | SHA-256 |
|---|---|
| Colocação integral C290 | `adc58125a13aa286371c127f41bf67b0ed4756e9ec2dc08bd2cb6e7ed754a000` |
| Recibo da derivação R01 | `80d71b6ee146be81c4e07c5b17dde0786effde6fa58ecd3268491eda6c810810` |
| Índice derivado R01 | `63b7a76c7063e51944ee8a6296aea43109a336330b3657ffa357cddb44b59813` |
| Manifesto derivado R01 | `acd49800bd428763297fbdfd5bb4f35d8d4af7803d850fdd8755760bfcb0faa5` |
| Recibo do construtor R01 | `ddeabdee9c60a0c5bc5eb4ec9726c864c800d066ec8c55bfccb41a412a2be2ba` |

A fixture construiu 108 cabeçalhos GGML sem armazenamento de pesos e chamou o construtor do pin C291 `c89c88b342054223e3f27a17fbfd0954803147ac`. Este aceitou as 4 608 entradas e abriu o pack com FD read-only e O_DIRECT, alinhamento de memória e de offset de 4096 bytes. Uma alteração de um byte na base do terceiro tensor da camada 35 provocou a recusa esperada. Houve zero chamadas a `pread` da TU. O chamador de produção `llama_moe_stream::open_files` faz ainda uma leitura de prova de 4096 bytes no GGUF antes de construir a store. A prova desta unidade termina no construtor. Workers, forward, latência de conversa e qualificação M3/M4 exigem outras evidências. [Fixture C291](native.cpp) · [Supervisor](native_gate.py)

## Contabilidade da memória

A derivação R01 chamou `setrlimit(RLIMIT_AS)` já dentro do interpretador. Os 650 912 KiB de `getrusage(RUSAGE_SELF).ru_maxrss` excedem o valor numérico de 524 288 KiB do limite estabelecido. Faltam o pico do espaço de endereços da própria imagem (`VmPeak`) e o seu pico residente (`VmHWM`) à entrada e à saída. O valor de R01 permanece publicado.

**REPRODUZIDO em memória anónima.** Após tocar 48 MiB num ancestral, a sequência fork → exec de prlimit → Python arrancou com limite de 32 MiB. A nova imagem reportou `VmPeak` de 15 744 KiB e `VmHWM` de 11 248 KiB, mas `ru_maxrss` de 56 420 KiB. Ao colocar GNU time entre prlimit e Python, o filho de time reportou `VmPeak` de 15 744 KiB e `VmHWM` de 11 244 KiB. Tanto GNU time como o filho reportaram 11 052 KiB de RSS máximo. O `wait4` do ancestral sobre time continuou a reportar 56 420 KiB. O ensaio demonstra um mecanismo suficiente para a discrepância. O histórico R01 não identifica a sua causa individual. [Contraprova sintética](test_usage.py)

**R02 pré-registado para a memória da derivação.** O lançador passa um limite hard e soft de 536 870 912 bytes a `prlimit` antes do exec, introduz GNU time como pai independente do interpretador e autentica o mesmo `derive.py` de R01 por SHA-256. No filho verifica o limite e os valores em `/proc/self/status` à entrada e à saída. O PASS exige `VmPeak`, `VmHWM` e máximo RSS medido por GNU time dentro do envelope, saída zero, integridade dos metadados e o resultado interno da derivação. A prova e os metadados recebem diretórios exclusivos distintos. A releitura do GGUF ou do pack, a compilação e o GPU têm orçamento zero nesta confirmação. [Lançador R02](usage.py)

Para repetir, apontar as variáveis para os artefactos Tesy selados e escolher dois destinos novos. `FROZEN` é a checkout limpa com o produtor de R01, `AUDIT` a checkout da correção. Manter o diretório dos metadados no destino definitivo para conservar a identidade do índice. A CLI do construtor está em `native_gate.py --help`.

```sh
python3 -IB "$AUDIT/usage.py" --usage-dir "$NEW_USAGE" \
  "$FROZEN/research/qualification-retake/packed_nvme_manifest/derive.py" \
  --commit b809f186e7df3ee8b8b4ef1d6d1e7550d222fdbe \
  --pack-placement "$PACK_RECEIPT" \
  --pack-sha256 adc58125a13aa286371c127f41bf67b0ed4756e9ec2dc08bd2cb6e7ed754a000 \
  --model-placement "$MODEL_RECEIPT" --c55 "$COPY_C55" \
  --runtime-manifest "$C283/expert-store-runtime.json" \
  --index "$C290/raw/integral-index.json" --readback "$C290/raw/full-readback.json" \
  --inventory "$C7/results/c7-20260927T1130Z/raw/gguf-inventory.jsonl" \
  --new-output-dir "$NEW_METADATA"
```

```sh
python3 -IB "$AUDIT/test_usage.py"
python3 -IB "$AUDIT/test_derive.py"
```
