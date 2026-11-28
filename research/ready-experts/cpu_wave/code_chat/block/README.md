# O verificador de três posições preserva a conversa de código?

**MEDIDO · GO para medir o custo.** No portátil, o mesmo 120B que gerou a conversa verificou uma proposta integralmente rejeitada e outra integralmente aceite. Em ambas, cada um dos 201 088 valores finitos de cada linha de logits coincidiu bit a bit com a referência serial que avaliou exatamente os mesmos inputs, incluindo as duas linhas do ramo rejeitado. O estado KV completo após o corte e as duas distribuições e estados KV seguintes coincidiram com o percurso serial que só avaliou as saídas verdadeiras. A nova biblioteca executou as 36 camadas do verificador. [Resultado por braço](result.json) · [Protocolo congelado](protocol.md)

| Braço | Agenda | Vetores completos capturados | Comparações passadas | Processo incluindo capturas |
|---|---|---:|---:|---:|
| R | GGUF original, três entradas seriais, remoção do sufixo | 11 | referência | 102,637 s |
| W | Pack e fusão CPU de produção, percurso serial verdadeiro | 9 | 18 | 89,867 s |
| OFF | Mesmo pack e fusão, biblioteca reparada, apenas o percurso verdadeiro | 9 | 39 | 89,839 s |
| ON | Mesma biblioteca, bloco de três, confirmação e correção pelo target | 11 | 57 | 90,428 s |

Os quatro processos reproduziram os 78 IDs de T1 até ao EOG, o corte real da cache nas 2 044 posições comuns, as duas chamadas de 5 e 56 tokens do prefill T2 e os primeiros 14 IDs da resposta de código. À posição 2 105, o estado confirmado continha 82 381 888 bytes. À 2 113, a aceitação dos dois tokens e a produção do terceiro deixaram 82 750 648 bytes. Cada comparação KV inclui a posição mínima, a máxima, o tamanho e o SHA-256 da serialização completa.

A rejeição também ilustra o custo do método. Até ao primeiro corte, W tinha completado 7 699 cargas e ON 7 757. Até ao segundo, os totais eram 8 120 e 8 158. As diferenças acumuladas de 58 e 38 cargas correspondem a 766 713 600 e 502 329 600 bytes lógicos de pesos. Estes contadores incluem o trabalho desde o arranque. Atribuir esses bytes a tempo de parede exige medir a conversa completa. O teste cobre greedy, estes dois prefixos e este hardware. [Decisão de arquitetura anterior](../README.md)

O antecedente de Leviathan et al. mede tradução e sumarização com T5-XXL denso, batch 1 e uma TPU v4. O resultado relevante para o Tesy é a dependência entre aceitação e custo da verificação. A nossa intervenção conserva uma só conversa, com experts MXFP4 repartidos por CPU, GPU e NVMe. O preço inclui as rotas dos tokens que depois são rejeitados. Consulta das fontes primárias em 27 de novembro de 2026. [Artigo, secção 4](https://proceedings.mlr.press/v202/leviathan23a/leviathan23a.pdf) · [Implementação de lookup do llama.cpp](https://github.com/ggml-org/llama.cpp/tree/master/examples/lookup)

A compilação demorou 4,046 s. Na primeira janela C55, o observador estava confinado a 384 MiB e a política admitiu apenas 256 MiB. Houve zero arranques. A janela seguinte mediu o contexto do portátil e admitiu 23 GiB antes de aplicar E20. A campanha durou 619,618 s com quatro inventários C118, pico até 15 849 603 072 B no cgroup, 6 848 MiB de VRAM e zero swap no cgroup. A integral da potência da GPU estima 5 304,6 J durante 369,925 s de cobertura. A energia total do portátil ficou desconhecida. O arquivo inclui os dois inventários, os 40 vetores completos de logits, os recibos de estado e as quatro execuções. [Comandos](commands.json) · [Manifesto privado](archive.json)

```sh
unit=research/ready-experts/cpu_wave/code_chat/block
python3 -IB "$unit/review.py" --check "$unit/result.json"
python3 -IB "$unit/test_grade.py"
python3 -IB research/qualification-retake/private_archive/verify.py "$TESY_CODE_CUT_ARCHIVE" "$unit/archive.json"
python3 -IB "$unit/review.py" --family "$TESY_CODE_CUT_ARCHIVE/part-01/tesy-code-cut-20261127-r01" --sha256 7616d59b0f9db28b0f65f6e482e4e22386675d2bd1ec5b06f2b87c577c967138 --new-output-dir "$NOVA_REVISAO"
cmp "$unit/result.json" "$NOVA_REVISAO/receipt.json"
```
