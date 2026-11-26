# Posse da origem até à conclusão das cópias de um backend

**GO para ligar o leitor à fixture numérica do pequeno grafo CUDA.** O protótipo C++ manteve os bytes válidos quando o consumidor guardou só o ponteiro e adiou a leitura até à barreira. A origem mapeada e a origem por pread usaram a mesma reserva e os mesmos pontos de sincronização. O proprietário abriu um descritor independente para o mesmo inode e o candidato aplicou FADV_RANDOM nesse descritor. O teste usa um ficheiro determinístico de 16 KiB. [Contrato e fronteira no pin do ik](protocol.md) · [Implementação](bank_input.hpp) · [Casos de falha](fixture.cpp)

Em cada modo, o primeiro consumidor verificou quatro transferências e 3 556 B com duas barreiras de IDs e uma de cleanup. O segundo verificou 51 B na sua própria drenagem. Um proprietário sem submissões encerrou sem acrescentar uma barreira. A tentativa de ultrapassar a reserva e os intervalos fora do ficheiro foram recusados. O consumidor conservou as duas transferências pendentes quando a submissão falhou depois de reter o ponteiro. A truncagem do ficheiro de fixture produziu uma leitura curta e o cleanup conservou os 64 B previamente enfileirados. Não houve carregamento de modelo, alocação de GPU ou pedido HTTP.

Reproduzido em árvore limpa no commit `7ea4ee4080ed82e6ebb44eade6ba7d27e1513d79`, com GCC 16.2.1 e verificações de comportamento indefinido em modo trap. O primeiro build falhou na ligação porque faltava `/usr/lib64/libubsan.so.1.0.0`. O segundo produziu o ELF `98adf8a4a156935c1a593e89afada394d317ecad8282d1e7b365de60655c5a02` e recibo `9ebb1e76f86dd346e9504b7ea7ee849c35572a2444480b0a4f5b1c98bbb02f6e`. A falha e a execução passaram a verificação do arquivo, com sete ficheiros e 266 868 B. [Lote 149](../../../../private_archive/part-149.json)

Para a ligação à fixture BANK9, o ponto de substituição é a submissão dos SET de matrizes após a sincronização dos IDs no mesmo backend. O controlo deve usar a mesma reserva e a origem mapeada, com o residente independente como referência. A prova inclui o endereço e o intervalo verdadeiros da cópia a partir de scratch, a origem GGUF da leitura explícita, os 66 quartetos e todos os 1 056 logits dos dois cortes físicos. A atribuição da origem depende ainda do carregador e do tempo de vida do backend durante o cleanup. A prova diferida acima abrange o componente isolado. O efeito no pedido de 153 tokens continua por medir. [Prova física que admitiu este protótipo](../layer-result.md)

```sh
python3 -IB research/qualification-retake/ik_mapped_experts/hybrid/cold_gate/backend_input/run.py \
  --commit 7ea4ee4080ed82e6ebb44eade6ba7d27e1513d79 --new-output-dir "$NEW"
```
