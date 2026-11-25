# A fusão sem contador poupa tempo à tile CPU0?

**INCONCLUSIVE.** A fusão ganhou ao corte por MMID nos seis blocos, por uma mediana de **2,003 ms**, e ao original C269 em cinco blocos. A mediana das reduções relativas contra o original foi **5,805%**, acima dos 5% exigidos. No quarto bloco a fusão ficou **1,756 ms mais lenta** do que o original. O pré-registo exigia os seis sinais positivos contra ambos os controlos. Esta família fica encerrada e não promove a candidata a uma campanha do 120B. [Protocolo e saída](protocol.md) · [Avaliação, braços e hashes](physical-r01/receipt.json)

| Bloco | Ordem | Original (ms) | Só MMID (ms) | Fusão (ms) | Original − fusão (ms) | Só MMID − fusão (ms) |
|---:|---|---:|---:|---:|---:|---:|
| 1 | O, M, F | 46,985 | 47,199 | 43,660 | +3,325 | +3,540 |
| 2 | M, F, O | 48,561 | 45,476 | 44,717 | +3,844 | +0,760 |
| 3 | F, O, M | 45,757 | 46,193 | 44,392 | +1,365 | +1,801 |
| 4 | F, M, O | 44,969 | 47,375 | 46,725 | −1,756 | +0,650 |
| 5 | M, O, F | 45,700 | 45,833 | 43,628 | +2,071 | +2,204 |
| 6 | O, F, M | 45,939 | 45,348 | 42,425 | +3,514 | +2,923 |

**MEDIDO.** A redução absoluta mediana contra O foi 2,698 ms. O, M e F começaram com a cache do manager vazia. A mesma rota genuína serviu cinco experts em cada processo. O usa a DSO histórica; M e F usam o mesmo ELF sem contador, com a única diferença entre esses dois tratamentos na opção de fusão. Por reinserção dos 485 bytes removidos da fonte do contador, o build recuperou a unidade de tradução da prova numérica anterior. Confirmou também a ausência do getter e do contador nos símbolos. Os três braços de qualificação anteriores aos blocos deram 48,341, 46,181 e 44,803 ms, sem participação na decisão.

Os 21 processos reproduziram byte a byte a referência independente, 92 160 F32 cada um. O intervalo medido inclui o serviço de experts durante o grafo e termina depois da sincronização. A variação entre processos não identifica a causa da perda do quarto bloco. Uma observação que separaria as duas hipóteses é medir a mesma tile com os cinco experts já admitidos e a mesma disposição de slots nos três tratamentos, cobrando e verificando a preparação separadamente; o confronto publicado aqui mantém as faltas originais. Uma utilização na conversa exigiria ainda comprovar custo e benefício no prefill com as densidades e estados reais. O caminho de uma posição de decode não beneficia desta fusão. [Aplicação real comprovada pelo contador](../real_tile/README.md) · [Piso histórico das leituras](../../prefill_read_floor/README.md)

## Proveniência e reprodução

Checkout física 9de344bc351b7a7f217b01a8898ceb92259c238d. DSO de timing e6805d92a99c8df2a0f0684338733e614da66e21efe5c6ab54f6ea11b5403f17, build e15f00f57365c2398f5a1c07ac0666898f5ee65a091ac8fe0dc4d1569613cc49. A família CPU terminou em **62,718 s**, incluindo **60,144 s** de C118; pico de **197 271 552 B**, zero swap e zero filhos no fecho. O orçamento de trabalho reconciliou **1 388 298 240 B** de E/S alinhada pedida e **7 741 440 B** de saídas. A cache de páginas e a concorrência interna dos quatro workers impedem interpretar bytes pedidos como tráfego físico. Zero GPU compute, zero carregamentos completos do GGUF e zero downloads nesta unidade.

O arquivo privado qualification-20261124-nvme-01/part-28 contém 97 ficheiros e 10 935 262 B, manifesto 5f6eebd455f902095a7e5ce3f9e2768ed7c876045caefecab9df468b540d4c80. O verificador reabriu as 21 tiles, os journals, os relógios e as saídas de processo. Produziu o mesmo compacto no destino original e após a recolocação nesse arquivo.

```sh
study=research/qualification-retake/parked_fusion/timing
python3 -IB "$study/profile.py" verify \
  --closed-run "$TESY_PART28/tesy-real-fusion-timing-20261125-r01" \
  --receipt-sha256 0d61b467450e7d49b88aab74cd97307423cbc0ff0072aba4bf30d0fd8d85a7af
```
