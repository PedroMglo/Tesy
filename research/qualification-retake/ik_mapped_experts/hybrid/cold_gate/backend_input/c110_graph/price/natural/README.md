# Um buffer de 648 MB e doze esperas adicionais nos dois turnos

**TRACE_DERIVED · GO para a fixture com reutilização limitada.** No replay de 6 880 sítios, o scratch fixado pelo C110 transborda em onze sítios do primeiro turno e num sítio do segundo, todos no prefill. Uma espera de conclusão em cada um desses doze sítios torna possível reutilizar os mesmos 648 155 136 B, conservando origem, destino, dimensão e ordem de cada SET. O custo de esperar pela RTX nesses pontos é desconhecido. [Contrato](protocol.md) · [Resultado por call e tile](result.json)

| Recorte | Sítios | Fills | SET de matrizes | Payload (GB) | Máximo vivo sem espera adicional (B) | Esperas adicionais |
|---|---:|---:|---:|---:|---:|---:|
| T1 | 5 013 | 14 885 | 41 394 | 196,768 | 1 018 294 272 | 11 |
| T2 5+148 | 211 | 3 238 | 9 708 | 42,804 | 701 263 872 | 1 |
| T2 primeiro decode | 36 | 92 | 276 | 1,216 | 52 936 704 | 0 |
| T2 decode completo | 1 656 | 3 987 | 11 961 | 52,705 | 52 936 704 | 0 |
| T2 até ao primeiro final | 1 795 | 7 079 | 21 231 | 93,579 | 701 263 872 | 1 |
| T2 completo | 1 867 | 7 225 | 21 669 | 95,509 | 701 263 872 | 1 |

T1 atinge o máximo na camada 0 da primeira tile da primeira chamada. A única espera extra de T2 ocorre na camada 0 da quinta tile da chamada de 148. Manter o intervalo de vida original em toda a conversa exigiria mais 370 139 136 B de scratch para este traçado. O maior SET individual, incluindo alinhamento, cabe em 35 254 272 B. No pior caso de geometria, até 128 experts em cada um de três papéis, reservar 1 693 974 528 B cobre qualquer seleção legal deste target. O banco do ik começa vazio antes de T1 por hipótese e mantém entre os dois turnos os seus slots e frequências. As rotas foram observadas no Tesy operacional. Os bytes e as esperas são projeções para esse trabalho, com a geometria e a política do ik.

O planner nativo a 288 slots coincidiu com o censo anterior em todos os sítios (SHA-256 `68f324758fc810f0aac21cc4c170c5d6ba7ea4fe914a8b41a68b7655611a2111`). No C110 reabriu os ranks físicos e reproduziu as 2 925 submissões na mesma ordem, por papel, offsets GGUF, slots, dimensões e geração. O pico de 648 155 136 B coincide com a medição física. Nas rotas naturais, o scratch cobre cada SET inteiro. O próximo teste força uma espera entre submissões ainda pendentes, verifica os bytes antes de reutilizar a origem e só depois admite a integração com o backend. [Ganho medido no C110](../README.md)

## Reprodução sem modelo

Commit `b584f6e5`. R01 sobre o arquivo e R02 sobre os journals originais produziram a mesma projeção, o mesmo código gerado e o mesmo ELF. O argumento do compilador identifica o diretório exclusivo de cada execução e está nos recibos. Sem arranque de modelo, GPU ou HTTP. [Arquivo dos dois replays](../../../../../../../private_archive/part-155.json)

```sh
python3 -IB score.py --p97 "$P97" --p106 "$P106" --numerical "$C110_R03" \
  --plan "$PLANO_120B" --ik "$FONTE_IK" --lib "$LIBGGML_CPU_PINADA" --new-output-dir "$NOVO"
```
