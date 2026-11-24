# Trabalho elegível no início da espera C317

**TRACE_DERIVED.** Quando já havia outra procura na fila e os quatro workers tinham trabalho atribuído, a cabeça FIFO tinha bytes prontos para cópia ou podia iniciar leitura direta em 133 das 334 observações. Nas restantes 201 havia uma segunda leitura em curso para a própria cabeça. Cada observação pertence a uma aceitação concreta dentro de um dos quatro traces. [Protocolo](protocolo-cabeca.md) · [Recibo](receipts/head.json)

| C317 trace-ON | Quatro atribuídos e procura na fila | Leitura direta elegível | Cópia READY elegível | Cabeça em READING | Dessas, passaram a READY até ao seu despacho observado |
|---|---:|---:|---:|---:|---:|
| nominal153-2 | 70 | 20 | 6 | 44 | 8 |
| nominal153-3 | 73 | 23 | 4 | 46 | 6 |
| code153-2 | 94 | 36 | 3 | 55 | 10 |
| code153-3 | 97 | 36 | 5 | 56 | 8 |

O auditor recompõe a fila primária por reserva/aceitação e valida que a primeira procura em fila foi a próxima aceite no controlo bloqueante. A secção crítica da aceitação identifica o prefixo de staging. Aplicar o `find` do pin à identidade da cabeça elimina tickets expirados. Uma entrada QUEUED cede à leitura direta; READY torna a cópia elegível; READING depende do produtor. Todos os destinos são confrontados com o tipo de serviço que a mesma geração recebeu no controlo. Esta classificação usa exclusivamente índices dos dois journals. O tempo para adquirir o worker, executar o serviço sob contenção, terminar a última publicação e drenar a conversa continua desconhecido. A decisão de latência permanece INCONCLUSIVE, a continuação NOT_RUN e o C317 nominal conserva o âmbito diagnóstico.

```sh
python3 research/worker-release-20261124/head.py --raw-dir "$TESY_C317_RAW" --new-output-dir "$out/head"
python3 -m unittest discover -s research/worker-release-20261124
```

O comando verifica tamanho e SHA-256 dos oito ficheiros antes de interpretar qualquer braço, reproduz a projeção corrigida e publica o recibo só num novo diretório. O protocolo exploratório anterior às contagens tem SHA-256 02aa5ee80853b39b877f7bdde8207b3159d1d1c6c84b21b004d45a758e1c2c35. Duas execuções em CPU demoraram 1,12 e 1,02 segundos, com pico de 84 872 KiB RSS, e produziram JSON idêntico de 3 532 B. Passaram os dez testes locais da unidade. O estudo usou zero execuções de modelo ou GPU.
