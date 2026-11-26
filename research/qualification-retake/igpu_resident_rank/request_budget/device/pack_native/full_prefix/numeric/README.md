# A captura integral do primeiro turno reproduz a referência numérica no 120B

**PASS para observar a próxima conversa.** No corpus C292 de 189 entradas e 32 passos fornecidos, duas execuções independentes do 120B com a nova biblioteca C291 reproduziram os mesmos 3 266 ficheiros da referência C270 e da C291 original, incluindo todos os cinco vetores de 201 088 logits. A biblioteca permaneceu a mesma entre OFF e ON. O observador ON conciliou 18 467 registos, 33 chamadas, 38 tiles, 7 768 linhas de quatro ranks e 4 501 reservas/publicações no perfil de T1. O alvo continuou responsável pelas escolhas. [Protocolo](protocol.md) · [Recibo por braço](receipt.json)

| Braço | Tempo de processo | Pico de cgroup | Pico GPU | CPU / GPU / NVMe máximos | Swap |
| --- | ---: | ---: | ---: | --- | ---: |
| OFF | 34,053 s | 17 904 553 984 B | 6 882 MiB | 69,25 / 52,15 / 46,85 °C | 0 |
| ON | 31,761 s | 17 023 365 120 B | 6 880 MiB | 68,00 / 52,36 / 49,85 °C | 0 |

Medição física E20 na árvore limpa `712adbc0553593607d955eb7b995e80f22bc4c11`. A C55 deu 61 amostras em 60,050 s e 22 817 013 760 B de cap canónico. Cada braço teve a sua C118 e confirmou o loader de 18 objetos, o FD direto do pack e o encerramento do processo. Estes dois tempos orçamentam a qualificação numérica; latência de produto exige a conversa. O teste sem pesos do corte 86→87 passou no manager real, incluindo os dois controlos negativos. [Fixture do corte](../README.md) · [Build e dados privados](../../../../../../private_archive/part-104.json) · [Família C292 privada](../../../../../../private_archive/part-105.json)

SHA do build `a125301f45a1a08c2774527d59c59ef09de5f4530fe9d6f8a80335288b2a5cad`, ELF `41471fc189711407e7d7ddaec96cfc78ff4b517acbded3046df74ef4d4258244`, família física `5f09f6228aa4b4bc1393331858bdccb04829c14e488827719374a33d35132d19`, revisão privada `43ea423cd4ad7aad659ad5288b9bc96159af18a241231cc6730163b2978e8a47`. Ambos os processos estavam inativos, MainPID=0, após o fecho. A consulta independente de nvidia-smi precisou da NVML 620.70.06 da sessão Tesy para corresponder ao driver carregado; o monitor qualificado usou essa mesma biblioteca.

```sh
python3 -IB "$NUMERIC/review.py" --family "$NEW_C292" --family-sha256 "$FAMILY_SHA" \
  --build-dir "$NEW_DSO" --build-sha256 "$BUILD_SHA" --original-family "$C291_PART54" \
  --r0-dir "$C270" --new-output-dir "$REVIEW_NEW"
```
