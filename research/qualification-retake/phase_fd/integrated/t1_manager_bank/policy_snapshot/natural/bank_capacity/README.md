# Quantas chaves pode a compressão acrescentar ao banco de T1?

**A bytes iguais, o cenário da amostra passa de 353 para 386 registos.** Para que o piso de volume do banco de publicações da parte 40 caiba no limiar nominal, pelo menos 31 das 33 entradas adicionais teriam de ser chaves distintas efetivamente necessárias e ausentes do primário inicial. O teste posterior sobre o prefixo selado encontrou cinco. Isso fecha a expansão isolada até K390 para o ramo D=47. Os picos históricos das partes 37 e 40 comportariam o mesmo K386 em formato cru se os restantes custos se mantivessem. [Pré-registo](protocol.md) · [Recibo aritmético](receipt.json) · [Teste da interseção](intersection/README.md)

| Envelope | Bytes disponíveis para o banco | Raw | Ideal da compressão da amostra | Amostra com tabelas e workspace | Todos os registos em fallback raw com o workspace do codec |
|---|---:|---:|---:|---:|---:|
| Mesmo orçamento atribuído a K353 | 4 720 263 168 | 353 | 392 | **386** | 348 |
| Calibração histórica mais exigente | 4 720 803 775 | 353 | 392 | 386 | 348 |
| Picos emparelhados da parte 37 | 5 167 247 295 | 386 | 429 | 423 | 382 |
| Pico do processo da parte 40 | 5 217 574 911 | 390 | 433 | 428 | 386 |

O limite do processo E20 é 21 474 836 480 B e o limiar de paragem é 20 937 965 568 B. A calibração usa os picos de 15 859 171 328 e 16 191 946 752 B, mais a provisão do PFJ1 de 25 165 888 B. Na parte 37 foram observados 15 745 503 232 B em OFF e 15 730 016 256 B em ON. O cálculo usa o maior entre o pico OFF mais o PFJ1 e o pico ON. Na parte 40 o pico observado com PFJ1 foi de 15 720 341 504 B. Os três orçamentos por processo reservam ainda 49 152 B para o novo sidecar e um byte para a desigualdade estrita no stop. A primeira linha isola a expansão comprada pela compressão na mesma provisão de RAM. O processo natural em curso precisa do seu próprio pico e dos custos de integração para admitir qualquer colocação física. [Calibração e regra de memória](../../../../host_cache/README.md) · [Pico com o banco projetado na parte 40](../../../../t1_bank_capture/README.md)

### O custo que entra nas contas

A amostra de 32 experts CPU e 32 CUDA soma 846 200 832 B crus e alinhados. O rANS espacial tem um piso de 761 647 104 B com tabelas gratuitas. O cenário mais cobrado reserva 763 453 440 B para a mesma amostra depois de incluir a representação esparsa das tabelas, o arredondamento por expert e a opção de guardar o registo raw. A projeção para K386 pressupõe uma mistura de tamanhos com aquela média e uma arena de comprimentos variáveis. O rANS que produza tais tamanhos, o custo de compactar a arena e a reconstrução no serviço continuam por medir. O NO_GO anterior dos 20% para reduzir os bytes de transporte na amostra mantém-se. [Amostra e limites por expert](../../../../../../mxfp4_spatial/README.md)

No ponto K386, os registos retidos ocupam 4 604 579 840 B. A montagem crua de quatro registos custa 52 887 552 B, o índice e etiquetas existentes 49 152 B e os novos descritores 28 672 B. Para os quatro workers, quatro buffers adicionais de saída raw e os histogramas/tabelas de trabalho de uma matriz de cada vez custam 57 360 384 B. O total é **4 714 905 600 B**, restando 5 357 568 B para desvios de tamanho, fragmentação e despesas omitidas. K387 excede o mesmo orçamento em 6 574 080 B. Quatro registos de montagem são necessários também no banco cru.

A amostra dá um teto de poupança para os 64 experts. Para experts arbitrários, o fallback pode conservar exatamente os bytes originais e dispensar as tabelas de codificação. A única capacidade uniforme desse desenho sob o orçamento fixo e os temporários prescritos é 348 chaves, cinco abaixo da baseline crua. Logo, a compressão oferece **zero entradas adicionais garantidas**. Garantir K386 exigiria medir os tamanhos reais das entradas retidas, controlar o pico ao publicá-las/substituí-las e prever a decisão causal quando o banco atingisse o limite de bytes.

### Uma condição que pode fechar a via sem construir o codec

O banco das **últimas publicações** tinha, em K353, um piso de 839 leituras até ao primeiro decode com reposição. Aumentar K para 386 mantém essas 353 chaves e acrescenta as 33 imediatamente mais antigas na mesma ordem de publicações distintas. Cada chave adicional pode eliminar no máximo uma leitura **obrigatória distinta**. O melhor piso possível é 806. O ramo de 47 permite 808, logo exige pelo menos **31/33 (93,94%)** das chaves adicionais úteis. Três chaves inúteis bastam para fechar esta variante nesse ramo. O ramo de 46 permite 865 e já admitia o piso anterior; nem esse piso nem os 31 acertos garantiriam a redução das releituras ou o desempenho no pedido.

O banco das **últimas vítimas** da campanha natural tem outra seleção. O teste pertinente do limite 31/33 preserva o banco por publicação e compara K353 e K386 no mesmo histórico, com os requisitos de T2 e a mesma restauração. Para as vítimas seria preciso calcular o piso da sua própria seleção. O formato e os bytes de cada leitura NVMe e os movimentos de entrega ao primário mantêm-se no denominador original. [Banco por publicação, incluindo as duas seleções controladas](../../../../t1_source_bank/README.md)

Protocolo em `f6b7c3c8`, código em `7b825871`. Duas execuções de 0,03 s cada sobre os JSONs versionados reproduziram o mesmo recibo `c35a0afbfbe947927e311100a84d2be883df7d41e026eb7a5ac1d06e27873147`. O RSS máximo foi 21 332 KiB. Zero novas leituras de pesos, journals ou GPU. Não houve ensaios de parâmetros.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/bank_capacity
timeout 10s prlimit --as=268435456 --cpu=10 --fsize=65536 -- \
  python3 -IB "$unit/screen.py" --new-output-dir "$NEW"
cmp "$unit/receipt.json" "$NEW/receipt.json"
```
