# A reutilização limitada preservou as cópias pendentes

**REPRODUZIDO · GO para o hook nativo do ik.** Os quatro braços da fixture compararam oito páginas com duas, para as origens DIRECT e PREAD_RANDOM. Em cada braço o consumidor diferido verificou os mesmos quatro SET e os mesmos 3 121 B na mesma ordem. O buffer maior fez três sincronizações. O de duas páginas fez quatro, incluindo a única espera adicional prevista. Foi verificado o endereço efetivo da origem, o deslocamento intrapágina, a separação de dois contextos e o drain final. [Pré-registo](protocol.md) · [Leitor C++](bounded_input.hpp)

Uma fatia individual demasiado grande foi rejeitada antes de libertar trabalho pendente. Uma falha de sincronização impediu a reutilização até ao drain final. Numa exceção após enqueue, o buffer ficou vivo até o consumidor verificar ambas as submissões. Uma leitura curta real, após truncar exclusivamente o ficheiro temporário da fixture, preservou a submissão anterior e impediu nova utilização do leitor. UBSan completou os quatro braços e os casos de falha. [Fixture](fixture.cpp) · [Recibo compacto](result.json)

Commit `bb6a43a9`, ELF `669372293e4c19c9e1a8d98e7f22f8ea17832b7ded9e7a2821d1e7e354858bea`. Quatro ficheiros privados, 46 468 B, zero pesos, alocações CUDA e pedidos HTTP. O relógio do cliente só é avaliado em conversa. [Manifesto 156](../../../../../private_archive/part-156.json)

```sh
python3 -IB run.py --commit "$(git rev-parse HEAD)" --new-output-dir "$NOVO"
```
