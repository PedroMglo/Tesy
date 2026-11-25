# O loader do ik preservou os experts mapeados num GPT-OSS sintético

**MEDIDO, GO para examinar a colocação híbrida.** Uma rede GPT-OSS artificial completou o primeiro decode CPU nos três processos com os mesmos 32 logits F32 finitos, bit a bit. O ficheiro tem duas camadas de atenção, sliding e global, 8 experts/top-4, largura e FFN 256, 4 cabeças e 2 cabeças KV de dimensão 64. As seis matrizes MXFP4 são separadas e os seis vieses F32 também. Em todos os braços, os endereços efetivamente devolvidos por `llama_get_model_tensor` cobriram integralmente as páginas read-only do inode correto e os offsets esperados. O teste observa o carregamento e o decode do fork através da API C. A tradução das opções CLI foi verificada noutra fixture. [Recibo](result.json) · [Ponte do frontend](../frontend/README.md)

| Processo | MAP_POPULATE no GGUF | WILLNEED integral | DONTNEED de páginas completas durante a carga | Threads antes/depois do contexto | RSS máxima, KiB |
|---|---|---|---:|---:|---:|
| OFF | Sim | Sim | 0 B | 1 / 1 | 43 364 |
| DEFER | Não | Não | 1 712 128 B | 1 / 1 | 43 044 |
| DEFER_PREFETCH | Não | Não | 1 712 128 B | 1 / 5 | 43 164 |

`mmap`, `madvise` e `posix_madvise` chamaram o SO e registaram os argumentos do ficheiro sintético durante a carga. Os dois intervalos DONTNEED com retorno zero começam nos offsets 872 448 e 2 531 328 e têm 856 064 B cada. São as páginas inteiras interiores às corridas contíguas de matrizes **e vieses** classificados como experts pelo loader. O artefacto tem 41 tensores, 3 390 592 B e SHA-256 `3771d5de5067095852a0132324c16b01e39c2b999082d4a3b6165e13aff90644`. Cada braço processou apenas o token sintético 7 na posição zero, em contexto novo. Os logits têm SHA-256 `d4a53844b37bff3fbfe97f576be5fb0895efd11654fed0311f1b0cdb72f62385` e greedy 25. A medição não quantifica faults, leituras do NVMe, o estado de KV após histórico ou tempo do cliente.

**O limite que mudou entre as duas identidades foi a reserva virtual.** Na R01, o braço OFF confirmou os offsets das 12 vistas e os dois pedidos de população integral antes de o scheduler tentar alocar 203 440 584 B. O máximo de 150 MiB de VA recusou essa alocação antes de executar o token. O pin reserva espaço para até 4 096 splits × 64 inputs × duas estruturas por entrada. Essa parcela não desaparece ao reduzir o modelo. R02 manteve o mesmo GGUF, cliente e bibliotecas, admitiu 768 MiB de VA por filho e impôs 150 MiB reais ao cgroup da família, com swap zero. O pico do cgroup chegou a 54 013 952 B (51,51 MiB), sem eventos max/OOM e com swap.peak zero. Todos os filhos terminaram com código zero; o scope acabou inactive/dead, Result=success. O RSS de R01 não foi capturado antes do abort. [Protocolo R01](protocol.md) · [Adenda prospetiva R02](resident.md) · [Reserva do scheduler](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/ggml/src/ggml-backend.cpp#L2759-L2775)

**Próxima fronteira.** O teste confirmou o caminho CPU com páginas do ficheiro e quatro workers no braço ativo. Continua a faltar, para colocação híbrida, saber que pesos permanecem mapeados antes do fill e qual ticket chega primeiro nas formas de prefill/decode. Para um resultado de produto é ainda necessária a referência numérica do GGUF original, incluindo o primeiro decode, e a qualificação com histórico e recursos do portátil. [Condições do comparador](../loader.md)

## Reprodução

O protocolo foi congelado em `abf4944d`, o cliente em `ca122be4`, a nova separação orçamento de VA/RAM em `84a931f2` e o seu supervisor em `6cca09b4`. Só o cliente foi compilado uma vez. O build em `/tmp/tesy-ik-tiny-loader-build-20261125-r01` tem recibo `e08c80b9b011bcde7575900c66fd41d058ed05920212e619499a98ea0b529956`. Os resultados de R01 e R02 estão em `/tmp/tesy-ik-tiny-loader-20261125-r01` e `/tmp/tesy-ik-tiny-loader-20261125-r02`, com SHA de recibo `4cace6b6464f09816ce2809ec3a8babb50d9fb8734758538b8acc7a2f912dd9d` e `b10222365dec972020668e3e9a9874018f8af2a7170ddef2c9f97ff60018cd92`. Testes locais voltam a gerar o artefacto e rejeitam uma vista ausente, hints integrais indevidos e um intervalo DONTNEED incorreto. [Testes sem modelo original](test_loader.py)

Em Linux com as duas bibliotecas CPU qualificadas, definir caminhos de saída exclusivos e o nome de scope com prefixo `tesy-ik-tiny-`. Os binários R03 ficam só em leitura.

```sh
module=research/qualification-retake/ik_mapped_experts/tiny_loader
src=/tmp/tesy-ik-source-20261125-r01
objs=/tmp/tesy-ik-ggml-build-20261125-r03/objects
python3 -IB -m unittest discover -s "$module"
python3 -IB "$module/run.py" build --source "$src" --objects "$objs" --new-output-dir "$build_dir"
build_sha=$(sha256sum "$build_dir/receipt.json" | cut -d' ' -f1)
systemd-run --user --scope --quiet --unit="$scope" -p MemoryMax=150M -p MemorySwapMax=0 \
  /usr/bin/python3 -IB "$module/resident.py" --scope "$scope" \
  --source "$src" --objects "$objs" --build "$build_dir" --build-sha256 "$build_sha" \
  --new-output-dir "$new_output_dir"
systemctl --user show "$scope.scope" --property=ActiveState,SubState,Result
```
