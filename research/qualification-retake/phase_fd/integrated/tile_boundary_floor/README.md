# Quais fronteiras obrigam a reler os pesos?

**NO_GO para mudar só o serviço dentro das tiles mantendo o primário de R0 em todas as fronteiras.** Com as últimas 353 vítimas disponíveis em RAM antes de T2, até uma cache de capacidade ilimitada durante cada tile precisa de pedir 985 experts ao disco no prefill 5+148. Isto excede as 808 leituras do cenário nominal de 47 saídas e as 865 da sensibilidade de 46. A 4,5 GB/s, o excesso nominal de payload corresponde a 518 ms. A diferença que importa para a engenharia está no estado que atravessa as tiles. [Protocolo congelado](protocol.md) · [Contagens por tile e tier](receipt.json)

| Banco de 353 antes de T2 | Igualdade após cada tile | Igualdade após as chamadas de 5 e 148 | Igualdade só antes do primeiro decode |
|---|---:|---:|---:|
| Vazio (0 entradas) | 1 133 | 874 | 852 |
| Últimas vítimas | 985 | 748 | 726 |
| Últimas publicações | 1 066 | 855 | 839 |

São mínimos **necessários** de admissões distintas, condicionados às chaves permitidas em cada corte, com 13 219 200 B de payload por admissão. O crivo concede permutas, cópias e todos os custos de construção e cálculo. Proíbe reservas adicionais de pesos que sobrevivam ao corte fora do banco e do primário acordados. A libertação de uma restrição de residência conserva os retornos externos, as geometrias de atenção e os consumidores. Não concede acesso antecipado ao router da próxima tile numa implementação. A tabela não mede a NAND nem a latência de uma conversa. O valor 748 com banco de vítimas deixa 178,299 ms no quociente de payload ideal da convenção 47; é uma condição necessária, ainda sem cobrar a capacidade real de 40 slots.

As seis tiles observaram 51, 326, 69, 199, 151 e 467 reservas físicas. Com as fronteiras preservadas e o banco de vítimas, as cargas compulsórias foram 34, 272, 59, 164, 99 e 357. Nos sete cortes havia 1 440 READY, zero LOADING e FIFO vazia. A união das procuras e dos residentes exigidos à saída foi confrontada com as admissões reais de cada intervalo. Os 1 440 descritores finais reproduzem os campos dos dois processos C281 independentes. Os tempos e bytes do decode mantêm os seus próprios denominadores. [Fronteira do primeiro decode](../t1_manager_bank/decode_entry/README.md) · [Ótimo com o primário limitado](../t1_primary_victim/README.md)

## Reprodução

Freeze de implementação b0216e97. Duas execuções deram o mesmo SHA-256 31c680ae31f11c7130ef3f71bf973ff69914bea7735cff5b1274bbf3ce980706 em 0,56 e 0,51 s, com pico RSS de 70 668 KiB. Usaram os recibos privados já selados, zero leituras de pesos e zero GPU. A seleção é recalculada exclusivamente a partir do prefixo anterior ao POST.

```sh
unit=research/qualification-retake/phase_fd/integrated/tile_boundary_floor
timeout 120s prlimit --as=536870912 -- python3 -IB "$unit/floor.py" \
  --part "$ARCHIVE/part-40" \
  --selection "$ARCHIVE/part-56/tesy-source-bank-seal-20261125-r01/selection.json" \
  --new-output-dir "$NOVA_SAIDA"
cmp "$unit/receipt.json" "$NOVA_SAIDA/receipt.json"
```
