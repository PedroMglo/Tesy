# Captura de uma linha de logits antes da amostragem

**PASS_SYNTHETIC_SERVER_LOGIT_OBSERVER.** Em duas execuções CPU, os 25 casos da fixture confirmaram o encaminhamento entre objetos ELF, a captura integral de uma linha finita de **201 088 float32** e a rejeição de capturas ambíguas. O processo devolveu ao chamador o ponteiro original e o `errno` deixado pelo fornecedor. A fixture verificou ainda o `errno` que o fornecedor recebeu na entrada. Houve zero forwards e zero utilização de GPU. A captura dos logits reais do GPT-OSS-120B em SWA completa pertence ao protocolo físico. [Protocolo](protocol.md) · [Recibo da segunda confirmação](fixture-r2/receipt.json)

## O que conta como linha crua

No servidor stock `e95426f1`, o chamador passa ao sampler o índice `slot.i_batch - off`. Para o primeiro pedido congelado de 16 IDs, com um único slot, a última posição tem índice 15. O observador aceita uma única chamada depois de o supervisor publicar `ARM` após READY. Verifica os parâmetros do modelo e do vocabulário antes de aceder aos dados. Nos índices 15 e −1, exige ausência de logits/probabilidades já amostrados e `LLAMA_TOKEN_NULL` para o token amostrado. A API admite um ponteiro de candidatos disponível nesse estado. [Amostragem no servidor](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/tools/server/server-context.cpp#L4894-L4904) · [Seleção dos logits no sampler](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/common/sampling.cpp#L134-L165)

O getter real para o índice 15 deve devolver o mesmo ponteiro que a base crua de `llama_get_logits(ctx)` e que o getter real para −1. Neste pin, −1 resolve para a última linha de saída e o vocabulário é não vazio. A coincidência com a base demonstra que essa é também a primeira linha. O observador verifica finitude, conserva a ordem dos IDs do vocabulário e publica os 804 352 bytes little-endian por criação exclusiva e ligação atómica. O recibo terminal sela a contagem de chamadas ao sair. O HTTP `n_probs` produz probabilidades normalizadas e ordenadas, ou logaritmos dessas probabilidades. Usá-lo para obter os valores brutos perderia informação e poderia mudar a seleção do sampler. [Implementação da captura](capture.cpp) · [Transformação HTTP](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/tools/server/server-common.cpp#L1664-L1712)

Os dois casos positivos reproduziram integralmente a referência sintética construída em Python, incluindo −0,0. Alterar um valor fora do máximo preservou o ID **4567** e alterou o SHA-256 da linha de `2f0126426ba7c7bde2eb2bea27e1dc34f8229bc0ecc9cdaef10eeb121b307a13` para `11ad71bcbe4a437de84e7cde3894112621fd0d463cc6d8bc418bfe074fdf7f00`. O modo desativado encaminhou todas as chamadas. No modo armado, as duas chamadas anteriores ao marcador ficaram fora da contagem do pedido. Os casos negativos cobrem, entre outros, vocabulário curto e modelo errado com buffer inacessível, fornecedor, chamador e índice errados, duas linhas, NaN/infinito no contrato de finitude (mutante executado com infinito), amostragem já aplicada, duplicação sequencial ou concorrente, perda de `ARM`, conflito no destino e saída abrupta sem recibo terminal. [Definição dos 25 casos](fixture.py)

## Proveniência e passagem ao servidor

O observador repõe o símbolo via `RTLD_NEXT`, confere o mapeamento executável por caminho canónico e inode e verifica o SHA-256 do objeto que contém o símbolo. As funções de introspeção devem resolver para a mesma imagem. A fixture usou o fornecedor sintético `e9cc255f3c499540977140713a6d2db60f94a05e93b60a38f3b40f5f8ea73634`. O perfil distinto `stock120b` exige o chamador `libllama-common` stock de SHA-256 `7cf9543328e80642d8c5d2212b1926fa5dc66f551d3d1e4cf04ab7900622c5e3`, o símbolo do sampler e um dos dois endereços relativos de retorno conferidos. Os fornecedores admitidos são o stock `717a7e3dc18ae58585c6df1af2454c5b441c171258b7100ae7e11530e02265b8` e o derivado `34ce470fac8b70d58602ba979f014616b9a8b7a9593b55a5e8436116f6ceb767`. O perfil stock rejeitou o fornecedor sintético antes de entrar em main. [Build do derivado e do controlo independente](../stock_prefault_build/README.md)

A campanha física precisa de autenticar externamente o GGUF, o processo que detém o listener, os seus mapas e o perfil de cache, o pedido e a posição reportada pelo endpoint. O marcador fica num diretório exclusivo desse braço até ao shutdown. O supervisor vincula o diretório ao PID verificado, exige o recibo terminal e compara o ID greedy devolvido com a linha. O próprio observador só materializa dados no PID em que foi inicializado. A referência numérica anterior em 16+1+1 usou SWA compacta. A referência para o servidor deve preservar o percurso do primeiro pedido com SWA completa e o mesmo envelope nos braços comparados. [Entrada selada](inputs.py) · [Verificador da comparação](compare.py) · [Resultado C110](../stock_numeric/README.md)

A confirmação partiu da revisão limpa `53083ebfc0c762a31eeb88fd710aec1c01ff3410`, árvore `91a4dee40df2192d27bd6a0984214361a094250b`. O observador teve o mesmo SHA-256 nas duas compilações, `9db495bdca8d60b1a14d162b5475dbd83b26d7c3574a29f5790c3f9d465d2b50`. Os resultados dos 25 casos, os digests das linhas e os quatro binários coincidiram. O único campo diferente nos recibos é `finished_utc`.

| Tentativa | Tempo total | RSS máxima | Saída privada | SHA-256 do recibo |
|---|---:|---:|---:|---|
| R01 | 1,48 s | 138 692 KiB | 5 732 410 B | `cf3ff7996245094e46d246faabc87e036d07b569385f55f7cf019a2e07cb1bf8` |
| R02 | 1,56 s | 138 284 KiB | 5 732 410 B | `76319a81b168c37eb828047779eb6d6d7eb8437a4ac9a490242288ab8809c6f4` |

Os relógios abrangem compilação e execução dos casos sintéticos. Cada reprodução requer dois destinos novos. [Recibo R01](fixture-r1/receipt.json) · [Recibo R02](fixture-r2/receipt.json)

```sh
python3 -B research/qualification-retake/stock_server_logits/fixture.py \
  --new-private "$NEW_PRIVATE" --new-output-dir "$NEW_COMPACT"
```
