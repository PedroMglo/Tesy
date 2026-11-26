# Codificação sem perdas do MXFP4 no C319

**NO_GO para codificar separadamente as escalas e os nibbles com o rANS marginal especificado.** Mesmo a componente mais favorável admite no máximo 13,256% de redução dos bytes, abaixo do gate de investimento de 20%. A amostra contém 192 matrizes em 64 experts e oito camadas, com 846 028 800 bytes de pesos. Os histogramas e denominadores são TRACE_DERIVED de C287/C319. A desigualdade é FORMAL para esta família de codificadores. [Protocolo](protocol.md) · [Derivação](prova.md)

| Pesos amostrados | Componentes | Máximo de poupança agregada | Melhor componente |
|---|---:|---:|---:|
| CPU | 96 | 8,714% | 13,256% |
| CUDA | 96 | 8,496% | 10,584% |
| Conjunto | 192 | 8,605% | 13,256% |

O melhor caso permite tabelas individuais gratuitas e descodificação instantânea. A passagem dos 4,52326 tok/s nominais medidos no NVMe a 6 tok/s exigiria cortar 24,612% do tempo por passo. A ligação entre bytes e latência é condicional à proporcionalidade de todo o tempo aos bytes. A origem dos histogramas e a desigualdade finita impedem estender o resultado a sequências arbitrárias. Um codec que explore dependência entre escalas e códigos abre uma hipótese diferente. [Recibo e estratos](evidence/receipt.json) · [Todas as componentes](evidence/components.json)

SSD-LLaMA avalia a compactação no percurso SSD–GPU e mede separadamente transferências e descompactação. Diferem o formato estudado e o caminho de entrega. PTWM implementa a separação de planos de escala e de pesos MXFP4 com codecs selecionáveis. A presente decisão isola o rANS de duas tabelas no MXFP4 original C319. Revisão em 25 de novembro de 2026. [SSD-LLaMA, §4](https://arxiv.org/html/2609.18110v1) · [Implementação PTWM](https://github.com/khwstolle/ptwm)

Reprodução sem modelo, numa árvore limpa em b5c438124f74447cf2c39b8107c9ad20b5ee9970. O manifesto de entrada, o código e o resultado por matriz estão autenticados no recibo. A execução levou 0,26 s e cerca de 24 MiB em CPU. A tentativa exploratória r01 encontrou a chave de tamanho legada do índice C287. O verificador foi corrigido antes da confirmação e os artefactos exploratórios foram preservados no portátil.

```sh
python3 -B research/qualification-retake/mxfp4_entropy/screen.py \
  --results-root "$C7/results" --new-output-dir "$NEW_OUT"
python3 -B -m unittest discover -s research/qualification-retake/mxfp4_entropy
```
