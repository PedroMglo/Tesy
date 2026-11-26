# Cache secundária na RAM no segundo pedido de uma conversa

**NO_GO para a L2 fria com a agenda primária R0 fixa, no cenário sustentado de 4,5 GB/s.** O prefill de 5+148 exigiu 1051 identidades distintas depois da entrada no pedido. Destas, 852 já faltavam no primário e 199 estavam residentes, foram expulsas e precisaram de nova entrega antes do consumo. O piso de **13 893 379 200 B** ultrapassa os dois orçamentos mesmo com capacidade ilimitada, entregas sem contenção e cópias gratuitas. Houve 693 identidades nas camadas CPU, 358 nas CUDA e zero gerações LOADING herdadas. [Protocolo](protocol.md) · [Recibo completo por fase e tier](evidence/receipt.json)

| Denominador no braço ON nominal | Orçamento condicional de prefill | Bytes a 4,5 GB/s | Excesso do piso | Mínimo já preparado em T1 |
| --- | ---: | ---: | ---: | ---: |
| 47 tokens previstos, M4 | 2,430748179 s | 10 938 366 806 | 2 955 012 394 B | 224 chaves, 2 961 100 800 B |
| 46 avaliações após primeiro token | 2,597414846 s | 11 688 366 807 | 2 205 012 393 B | 167 chaves, 2 207 606 400 B |

O mínimo em T1 pressupõe escolher perfeitamente as chaves úteis e mantê-las acessíveis até à consulta. Cada chave exige a materialização anterior de 13 219 200 B, espaço de retenção e entrega ao primário. A captura começou em T2. Uma L2 morna fica **NOT_RUN** até haver prova dessa seleção e do seu custo em T1. Outra condição de reabertura seria demonstrar serviço sustentado suficiente nas janelas relevantes. Só o piso de payload requer 5,716 ou 5,349 GB/s, respetivamente, concedendo o orçamento inteiro ao transporte. [Dois denominadores](../conversation/denominadores.md)

## Política de retenção

Reprodução causal da ordem real de reivindicação e publicação. Os contadores de hits têm como denominadores 1263 cargas de prefill (808 CPU e 455 CUDA) e 1091 de decode (786 CPU e 305 CUDA). O crivo exige 219 hits no decode. As duas capacidades finitas cabem na folga contemporânea estimada de 5 167 296 448 B ao limiar de paragem do E20. Os custos incluem quatro buffers de montagem, alinhamento, índice e etiquetas.

| Slots L2 | RAM adicional | Hits prefill CPU/CUDA | Bytes devolvidos pelo FD ainda necessários até ao retorno 148 | Hits decode CPU/CUDA | Fração decode |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0, R0 | 0 | 0 / 0 | 16 711 176 192 | 0 / 0 | 0% |
| 239 | 3 212 959 744 B | 15 / 17 | 16 287 772 672 | 31 / 3 | 3,12% |
| 353 | 4 720 263 168 B | 42 / 40 | 15 626 199 040 | 43 / 5 | 4,40% |
| 4608, ilimitada para o universo do modelo | 60 979 666 944 B | 115 / 97 | 13 906 173 952 | 320 / 101 | 38,59% |

No caso de 353 slots, as faltas obrigariam a copiar **29 399 500 800 B** para montagem ao longo de T2. Os hits entregariam mais **1 718 496 000 B** ao staging original para poupar **1 720 107 008 B** de retornos do FD. Permanecem **31 117 996 800 B** de cópias para os destinos primários. Das 2224 inserções, 2108 terminariam o pedido sem um hit posterior. Estes são custos de movimento de payload derivados da trajetória. O sinal de custo do observador T2 ficou dentro da banda emparelhada. Nenhum braço executou uma L2 física. O estudo mede retornos de pread no FD do GGUF e não proporciona segundos de aceleração, tráfego NAND nem validação do caso de código. [Crivo histórico de decode](../../../l2_read_admission/README.md) · [Dois dispositivos](../../../dual_store/README.md)

## Reprodução

O protocolo foi congelado em `d91d1968` e o primeiro código em `96036db1`. R01 encerrou após 0,19 s e 47 732 KiB com erro de nome local na avaliação dos denominadores. A correção em `e2fcb7ac329cf186da44bd45ffcc1c5e9b8023ad` mudou o nome da variável; seis testes incluem o caminho completo das duas decisões. R02 e R03 usaram diretórios exclusivos e concluíram em 0,20 e 0,21 s, com RSS de 47 444 e 47 724 KiB. Os recibos são idênticos, SHA-256 `a3398265b4bf33ed75f4898b346c2d9a988865cd5ca9cf98668826b52d41f700`. [Falha R01 preservada](evidence/r01-fail.json) · [Código](screen.py)

A partir da raiz e com os dois diretórios privados autenticados, repetir o comando com um destino novo. O verificador confere o journal `1a96cca8…35f018`, a conservação e a prova do FD da campanha física. A reprodução usa somente CPU e ficheiros de resultados.

```sh
timeout 120s prlimit --as=536870912 --cpu=120 --fsize=1048576 -- \
  python3 -IB research/qualification-retake/phase_fd/integrated/host_cache/screen.py \
  --off "$OFF" --off-sha256 171e90939e42a55ce51b196224ecc2bb008cc7408205eae7e961d09759cdfc5f \
  --on "$ON" --on-sha256 78c3a5bb34353d2b880b14bfa80634cd06dfe465beec529446206a8728af3f43 \
  --new-output-dir "$NOVO"
```
