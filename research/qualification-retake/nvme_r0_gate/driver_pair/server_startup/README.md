# Arranque dos executáveis C270 e C281 sob o driver 620.70.06

**REPRODUZIDO — `PASS_STATIC_C270_C281_DRIVER_SELECTION` em dois ensaios.** Na estação com o módulo NVIDIA 620.70.06 carregado, o interpretador GNU resolveu as 17 dependências nomeadas do C270 e as 23 do servidor C281 com os nomes e SHA-256 do controlo contemporâneo de novembro. Nos dois casos, `libcuda.so.1` veio do deployment OSTree assinado `08d80c49…6c136cc4`. O interpretador foi autenticado à parte. O kernel fornece a vDSO em memória. [Protocolo congelado](protocol.md) · [Origem do deployment](../origin-note.md)

| Executável | Dependências verificadas | SHA-256 do executável |
|---|---|---|
| C270, captura numérica P12/slots40 | 17 dependências, incluindo os cinco ELF numéricos C269 | `acbb3d1d81ac4b9f8f493c97dd689333165abf85119178bca48decaceffa5758` |
| C281, servidor persistente | 23 dependências, incluindo a implementação do servidor C276 e os ELF partilhados com C270 | `054e983528d35731e2dc6222f1418f2f08120ef83e0c5f2a8db11805dd38effa` |

Cada identidade criou quatro aliases privados para libcuda, PTX JIT, NVVM e gpucomp. O primeiro fornecedor disponível para cada nome na lista de diretórios do filho veio do deployment selado. Só libcuda figura nas dependências de arranque dos dois executáveis. A configuração do monitor usou um quinto alias, para NVML, num diretório independente. O verificador autenticou o executável de nvidia-smi, o SONAME, o build ID, os bytes e a origem OSTree dos cinco objetos e o build ID do módulo ativo. A busca opcional de libnvcuextend continuou sem fornecedor nos diretórios candidatos e no deployment. As listagens estáticas deixam por observar a telemetria e os dlopen do processo real. A R02 anterior observou essas inicializações no seu próprio grafo sintético. [Fixture de kernel](../mixed-r02.json)

**Custo.** Cada ensaio calculou o digest de 973 115 848 B em 31 ELF distintos, com uma única passagem por identidade. A R01 demorou 0,645 s e atingiu 21 276 KiB de RSS. A R02 demorou 0,634 s e atingiu 21 648 KiB. O máximo é o maior pico individual de `RUSAGE_SELF` e `RUSAGE_CHILDREN`. O verificador invocou o interpretador em modo `--list` e executou zero forwards. As duas tabelas públicas coincidiram integralmente. Os mapas privados também coincidiram após substituir apenas o nome da raiz exclusiva de cada ensaio. Os digests distintos de cada mapa permitem validar os caminhos exatos no respetivo instante. [Recibo R01](r01/receipt.json) · [Recibo R02](r02/receipt.json)

Para reproduzir numa checkout limpa com as dependências originais, reservar um destino privado inexistente. O programa autentica o código dos auxiliares, os contratos e os bins a partir da checkout e grava o SHA da árvore e do programa no recibo. A confirmação usou commit `3b6c520d1d3113e22263ddb4f047b4b2b8f72f61` e árvore `c8de587d0bc7c27209481dace8db43a8c7d90576`.

```sh
study=research/qualification-retake/nvme_r0_gate/driver_pair/server_startup
python3 -IB "$TESY_CHECKOUT/$study/screen.py" \
  --repo "$TESY_CHECKOUT" --new-output-dir "$NOVO_RESULTADO_PRIVADO"
```

O novo perfil de C270 pode usar o recibo e o SHA do mapa como entrada para validar novamente os objetos no seu próprio ambiente, obter C55/C118 e verificar os carregamentos efetivos do processo. A prova numérica continua a exigir os 1 500 payloads e os cinco vetores C127. O par natural C281 conserva a autoridade do histórico, dos IDs de entrada e dos validadores. Um testemunho dos IDs realmente amostrados exige um gate próprio. O estado operacional é M3 PARTIAL e M4 NOT_MET. [Gate numérico](../../README.md) · [Conversa natural](../../../nvme_conversation/README.md)

A janela física subsequente observou 62 amostras em 61,000 s. O mínimo canónico de memória disponível foi 26 330 464 256 B. A política admitiu 22,5 GiB com reserva de 2 GiB. O máximo foi de 44,125 °C na CPU e 39,99 °C na GPU, com zero processos de compute concorrentes. [Protocolo da execução E20](physical-protocol.md) · [Arquivo das duas listagens e da janela](../../../private_archive/part-22.json)
