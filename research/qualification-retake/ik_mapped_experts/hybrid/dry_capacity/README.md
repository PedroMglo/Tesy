# O dry-run omite as vistas que ativam o banco de experts

**NO_GO para qualificar a capacidade do banco CUDA através do dry-run deste pin.** Duas execuções do mesmo cliente CPU com o GPT-OSS sintético deram resultados idênticos. A carga normal ligou todas as seis matrizes MXFP4 aos offsets certos no GGUF. Em dry-run, os seis descritores mantiveram nome, forma e tipo, mas todos tinham `data == nullptr` e `buffer == nullptr`. Os dois modos devolveram um modelo. Para medir a reserva de memória do banco, o próximo cliente tem de demonstrar que encontrou camadas elegíveis e criou os slots pedidos. [Recibo compacto por tensor](result.json) · [Protocolo](protocol.md)

| Braço CPU, por execução | Matrizes | Buffer WEIGHTS no host | Bytes ligados às seis vistas | Contextos / forwards |
|---|---:|---:|---:|---:|
| NORMAL | 6 | 6 | 1 671 168 | 0 / 0 |
| DRY | 6 | 0 | 0 | 0 / 0 |

O caminho mmap cria um buffer para a região do ficheiro. A associação de cada tensor ocorre em `load_all_data`, que o modo dry-run salta. A seleção das camadas para a cache GPU exige um buffer WEIGHTS no host para cada matriz. Se todas forem inelegíveis, o construtor do banco pode regressar com o banco inativo. A experiência testou diretamente a associação no loader CPU. A inferência sobre a elegibilidade vem do predicado comum do pin. A memória efetiva de um contexto GPU e os custos de um forward continuam por medir. [Criação do buffer por intervalo](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama.cpp#L5427-L5440) · [Desvio em dry-run](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama.cpp#L5609-L5618) · [Atribuição ao tensor](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama-model-loader.cpp#L1886-L1891) · [Critério de camada e cache inativa](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama-moe-cache.cpp#L158-L192)

O protocolo foi congelado em `4a0bff13` e o cliente em `d77d80b0`. Em cada reprodução o namespace só expôs a fixture, o executável e as bibliotecas CPU. A VMA foi confrontada com um descritor aberto do mesmo ficheiro. Ambos os recibos completos deram SHA-256 `8a213f692a5eb5522529fbf4de617c1400d53bb4755fef34570e7e20646b6708`. As saídas ocuparam 52 425 e 52 423 B. Da criação do log de compilação à gravação do recibo passaram 0,530 e 0,482 s pelo relógio do filesystem. Não houve leitura de pesos do 120B nem acesso à GPU.

```sh
python3 -IB run.py --source "$IK" --objects "$CPU_R03" --tiny "$TINY_GGUF" --new-output "$NOVO"
```
