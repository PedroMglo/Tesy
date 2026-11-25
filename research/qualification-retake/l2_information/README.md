# Quando é preciso admitir um expert na L2

**NO_GO para esperar pela segunda publicação ou começar o decode com a L2 vazia em I.** Com o primário R0 fixo, qualquer política que satisfaça o limiar de 20% nos 32 passos de decode precisa de pelo menos **194 hits no nominal e 170 no código** provenientes da primeira publicação da chave desde P. Precisa também de transportar através de I os experts que servirão pelo menos **185 hits no nominal e 239 no código**. Um expert retido logo na primeira publicação durante o incremento pode satisfazer as duas condições no mesmo hit. Os mínimos contam hits de decode e não se somam. [Protocolo e âmbito](protocol.md)

| Braço trace-ON C294 | Lookups no decode | Limiar de hits | Ótimo integral com 243 / 378 entradas | Máximo sem reter a primeira publicação | Máximo com entrada fria em I | Máximo com ambas as restrições |
|---|---:|---:|---:|---:|---:|---:|
| nominal153-2 | 1 081 | 217 | 275 / 292 | 23 | 32 | 17 |
| nominal153-3 | 1 081 | 217 | 275 / 292 | 23 | 32 | 17 |
| code153-2 | 1 308 | 262 | 266 / 401 | 92 | 23 | 14 |
| code153-3 | 1 308 | 262 | 266 / 401 | 92 | 23 | 14 |

Os três máximos restritos coincidiram nas duas capacidades. Por exemplo, uma entrada fria deixa no máximo 23 hits no código, pelo que pelo menos 262 − 23 = 239 têm de aproveitar uma publicação anterior a I. No nominal a conta correspondente é 217 − 32 = 185. Com ambas as restrições em simultâneo, pelo menos 200 hits nominais e 248 de código teriam de usar alguma das oportunidades excluídas. O recibo identifica as duas repetições de cada caso e a origem CPU/CUDA de cada classe. Os máximos isolados por dispositivo atribuem toda a capacidade ao dispositivo em causa. [Resultados e digests por braço](evidence/receipt.json)

**TRACE_DERIVED.** A L2 codificada começa vazia no fim do prefixo P. Cada intervalo começa na publicação P10 anterior da chave (camada, expert) e termina na próxima reivindicação de serviço P5 durante o decode. O oráculo pode conhecer as rotas futuras, recusar qualquer admissão e manter os bytes em staging gratuitamente até P10. A capacidade de 243 entradas corresponde ao orçamento de payload de 3 GiB. A de 378 usa o saldo de payload favorável do envelope E20. Com 243 entradas, o ótimo integral em código fica apenas quatro hits acima do limiar. Uma política causal candidata teria de identificar cedo as cópias úteis e mantê-las até à consulta com custos de memória, cópia e coordenação medidos. Os relógios de produto e os estados M3 PARTIAL e M4 NOT_MET conservam a sua avaliação anterior. [Oráculo e políticas de admissão](../l2_read_admission/README.md)

**Reprodução.** Os dois replays saíram da árvore limpa `a68fdd4b0b6e6a78b9ef9e9f072770b7592c0f01` (árvore `59d057a30a3dcb65271abf62e391d46982fcca15`). As saídas privadas `m4-l2-information-20261125-r01` e `m4-l2-information-20261125-r02` produziram o mesmo SHA-256 de recibo, `0e9db779ae78f291ae481ddddd4b02e86f9082b6ac2c7a681a152c337d60be33`. Cada execução demorou 0,46 s, com RSS máximo de 47 872 e 47 616 KiB, respetivamente. O verificador autenticou o recibo da admissão L2, os scripts anteriores e os ficheiros dos quatro braços a partir do manifesto C294. Os dois testes sintéticos cobrem as quatro classes de publicação e a sobreposição dos mínimos. Zero pesos ou GPU. [Verificador](screen.py) · [Testes](test_screen.py)

```sh
OPENBLAS_NUM_THREADS=1 python3 -B research/qualification-retake/l2_information/screen.py \
  --raw-dir "$TESY_C294_RAW" --new-output-dir "$TESY_NEW_OUTPUT"
```
