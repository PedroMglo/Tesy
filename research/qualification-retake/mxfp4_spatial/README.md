# Quanto acrescenta o nibble anterior à compressão exata?

**NO_GO nos 64 experts C287.** Mesmo com tabelas gratuitas ajustadas por matriz e descompressão instantânea, o rANS que condiciona o nibble à escala, à metade do bloco e ao nibble anterior na mesma linha só pode poupar **9,992%** dos bytes dos registos alinhados. Nenhum dos 64 experts chega ao gate de 20%. Esta família fica encerrada antes de implementar ou cronometrar um descodificador. [Pré-registo](protocol.md) · [Recibo](evidence/receipt.json)

| Destino | Experts | Bytes raw alinhados | Piso de bytes codificados e alinhados | Teto de poupança agregada | Melhor expert |
|---|---:|---:|---:|---:|---:|
| CPU | 32 | 423 100 416 | 380 682 240 | 10,026% | 12,515% |
| CUDA | 32 | 423 100 416 | 380 964 864 | 9,959% | 10,905% |
| Todos | 64 | 846 200 832 | 761 647 104 | 9,992% | 12,515% |

**MEDIDO** nos bytes MXFP4 originais: 45 362 contextos ocupados somando as 192 matrizes, com início de linha e ordem baixo/alto conferidos. Agregar os histogramas espaciais por escala reproduziu os digests do antecessor em cada matriz. **FORMAL** para os dois estados byte-rANS definidos: aplicar a desigualdade finita a cada stream, somar os três pesos, arredondar o registo a 4 096 B e admitir fallback raw. Com esse mesmo arredondamento, o teto do modelo que conhece apenas a escala é 9,766%. O novo contexto acrescenta 0,226 pontos percentuais. Os biases residentes foram autenticados separadamente. [Prova da desigualdade](../mxfp4_entropy/prova.md) · [Controlo condicionado à escala](../mxfp4_conditional/README.md) · [Resultados por expert](evidence/experts.json)

As tabelas tiveram custo zero no cálculo desse piso. Por exemplo, uma implementação com frequências de 16 bits e normalização de 4 096 pode representar as tabelas densas em 279 040 B por matriz; armazenar as tabelas ocupadas e uma chave de três bytes por contexto soma 1 685 974 B nas 192 matrizes, antes de índices, estados e tabelas de descodificação. Um código que consulte essas frequências precisa de as transmitir ou aprender fora da avaliação. Nenhum fluxo comprimido foi produzido.

### Orçamentos da conversa nominal

Mantendo 4,5 GB/s úteis e o decode exatamente em 6 tok/s, conceder a **cada** admissão o melhor registo entre os 64 (11 567 104 B) deixa os resultados abaixo. São sensibilidades sobre os misses desses pedidos; a compressibilidade dos experts que não pertencem à amostra continua desconhecida.

| Sessão, hipóteses e número de admissões | Orçamento (B) | Volume favorável (B) | Excesso (B) |
|---|---:|---:|---:|
| Parte 37, mesmas 1 263 admissões de 5+148 | 10 938 366 806 | 14 609 252 352 | 3 670 885 546 |
| Parte 40, banco das últimas publicações e prioridade, 1 160 incluindo reposição | 10 690 306 614 | 13 417 840 640 | 2 727 534 026 |
| Parte 40, retenção posterior ilimitada, piso de 839 | 10 690 306 614 | 9 704 800 256 | −985 506 358 |

A última linha tem folga de volume num problema ideal. A política executável simulada tem 1 160 admissões. O efeito na latência real continua desconhecido. Uma reabertura requer informação diferente, por exemplo dependência entre linhas que sobreviva ao acesso independente do expert, e margem de volume para cobrar tabelas, reconstrução bitwise, cópia aos destinos e espera pela publicação. [Parte 37](../packed_nvme_manifest/server_profile/product-protocol.md) · [Parte 40](../phase_fd/integrated/t1_source_bank/README.md)

### Reprodução

Protocolo selado em `b8d4636f75affc609bf046ed5cb60e30bec8e98c` e código em `b0216e9723828519106fe4b78bf29000b0ce6c97`. Dois processos sequenciais leram cada um 848 560 128 B do pack local C287, autenticaram o ficheiro completo e os 384 componentes. R01 e R02 levaram 5,65 e 4,27 s com RSS máximo de 64 340 e 64 012 KiB. Os recibos e os resultados por expert coincidiram byte a byte nas duas execuções, com SHA-256 `b40f8f9c97d5d4d5f50723bcc8cd4feb72e8ae0990c271de8477553f6977575c` e `4a893ad344dc865f05bc292a3206aae9f655056746d7d3c61bbe7889c44eed98`. Zero forwards, leituras do GGUF integral ou uso de GPU.

```sh
study=research/qualification-retake/mxfp4_spatial
python3 -IB "$study/test_screen.py"
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  timeout 245s prlimit --as=402653184 --cpu=240 --fsize=8388608 -- \
  python3 -IB "$study/screen.py" --results-root "$C7/results" \
  --sample-pack "$C7/results/c283-exact-expert-service-epoch-20261006T194311Z/pack/sample64-v1.bin" \
  --new-output-dir "$NOVO"
cmp "$NOVO/receipt.json" "$study/evidence/receipt.json"
cmp "$NOVO/experts.json" "$study/evidence/experts.json"
```
