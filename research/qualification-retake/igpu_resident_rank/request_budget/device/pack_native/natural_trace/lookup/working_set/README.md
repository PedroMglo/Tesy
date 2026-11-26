# Quanto teria de ser lido para servir as 11 verificações B3?

**No P observado, as 11 verificações cobrem 520 leituras AR.** Conservando a rota dos inputs conhecidos e devolvendo a residência R0 à saída de cada bloco, continuam a ser necessárias pelo menos **508 aquisições**, 353 na CPU e 155 nas camadas CUDA. A união por bloco poderia eliminar no máximo 12 dessas leituras (2,31%) sob estas premissas. Para reproduzir só os proprietários de saída, independentemente das rotas B3, o piso é 463. Nenhuma das 11 verificações precisa de uma identidade de restauro adicional às que as rotas conhecidas já pediram. Movimentos de slots, esperas e custos reais de restauro permanecem por medir. [Recibo compacto](evidence.json) · [Protocolo](protocol.md)

| # | Calls AR substituídas | Linhas conhecidas | Leituras AR observadas | Piso para devolver o carry | Piso com rota e carry |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | 3 | 1 | 19 | 19 | 19 |
| 2 | 12–14 | 3 | 87 | 79 | 83 |
| 3 | 17–19 | 3 | 50 | 46 | 49 |
| 4 | 20–22 | 3 | 94 | 81 | 91 |
| 5 | 23 | 1 | 13 | 13 | 13 |
| 6 | 26 | 1 | 15 | 15 | 15 |
| 7 | 30 | 1 | 30 | 30 | 30 |
| 8 | 38–40 | 3 | 80 | 64 | 77 |
| 9 | 42–44 | 3 | 67 | 57 | 66 |
| 10 | 45–47 | 3 | 55 | 49 | 55 |
| 11 | 48 | 1 | 10 | 10 | 10 |
| **Total** | | **23** | **520** | **463** | **508** |

Nas seis aceitações integrais conhecem-se os três inputs AR. Nas cinco rejeições da primeira proposta, o único input conhecido é a âncora. As duas linhas seguintes executariam entradas especulativas; o crivo concede-lhes custo zero. A correção emitida pela primeira linha alimenta uma ação posterior. O estado de entrada de cada ação deriva do retorno anterior. Todos os cortes foram drenados e os 108 pesos foram confrontados com a colocação real. No prefill original houve mais 51 e 1 212 leituras, nas calls de 5 e 148; nas 23 AR conservadas houve mais 571 (423 CPU, 148 CUDA). Estes custos já pertencem às fases do cenário temporal que as mantém e que retira a fração selecionada dos seus remaps. [Crivo temporal das duas intervenções](../protocol.md)

**O primeiro final é o limite mais apertado.** A peça chega após a call 46, durante o décimo bloco. Mesmo admitindo a entrega antes da terceira linha e adiando o restauro desse bloco, conhecem-se 484 aquisições (6 398 092 800 B úteis). Se o bloco calcular todas as linhas antes da entrega, o piso sobe a 498 (6 583 161 600 B). No decode completo as 508 representam 6 715 353 600 B úteis ou 6 716 719 104 B de pedidos ao FD.

| Cenário com exteriores fixos | Preço mínimo a 4,5 / 8 GB/s | Verba restante por verificação se recuperar 50% dos remaps, a 4,5 / 8 GB/s | Idem, recuperando 100% |
| --- | ---: | ---: | ---: |
| Primeiro final, entrega parcial, 10 verificações | 1,422 / 0,800 s | −103,46 / −41,26 ms | 364,57 / 426,78 ms |
| Primeiro final, bloco completo antes da entrega | 1,463 / 0,823 s | −107,57 / −43,57 ms | 360,46 / 424,46 ms |
| Decode completo, 11 verificações | 1,492 / 0,839 s | 308,69 / 368,05 ms | 466,05 / 525,40 ms |

A velocidade é um teto hipotético de transporte por um único recurso, durante cada verificação serial. A conta credita toda a restante verificação como gratuita antes de apurar a verba. Recuperar 50% dos remaps das calls que permanecem é insuficiente para 10 s ao primeiro final, inclusive com exteriores gratuitos: faltariam 0,884 s a 4,5 GB/s ou 0,262 s a 8 GB/s no caso de entrega parcial. Mesmo cobrando só as 404 identidades de saída já vencidas no corte e tomando 8 GB/s, faltariam 0,130 s com os exteriores gratuitos. A 100% há margem condicional. Para a primeira peça com exteriores fixos e os ranks conhecidos, a fração mínima por interpolação linear, ainda com o resto do verificador gratuito, é 61,05% a 4,5 GB/s ou 54,41% a 8 GB/s.

Outra política que mantenha uma fonte secundária, altere o carry ou antecipe leituras entre verificações terá outro orçamento. Igualdade dos IDs de saída não demonstra a mesma rota em B3. A execução das linhas rejeitadas, o custo do rollback e a continuação numérica no target são pré-condições para atribuir o ganho a uma implementação. [Fixture das decisões](../../../../../../../history_lookup/native_ids/b3_fixture/README.md) · [Contraprova numérica](../../../../../../../history_lookup/b3_numeric/README.md)

## Reprodução

```sh
prlimit --as=536870912 --cpu=120 -- python3 -IB screen.py \
  --family-dir "$FAMILIA" --family-sha256 "$SHA_FAMILIA" --new-output-dir "$NOVO"
python3 -IB test_screen.py
```

O protocolo foi congelado em `55f83531`; as duas execuções da checkout `df0bae6652570e7e24c2a613d503be327d35450f` e uma terceira a partir da part-97 emitiram os mesmos 53 914 B, SHA-256 `9a272dd0c0b876cd419b1d3ecbeebfe13f4f4829711527601eb59a02ef667518`. Correram em 0,37 / 0,37 / 0,39 s, com pico máximo de 64 244 KiB RSS. As três terminaram sem falha ou corte ambíguo. O compacto mantém as contagens por bloco/tier, os digests do estado e as folgas totais em ns; a verba média da tabela é a folga dividida por dez ou onze. Os quatro testes exercitam união, restauro, rejeição, digest/geração de slot, corte parcial e contabilidade temporal. O SHA do manifesto part-97 é `a649b2e520fcbcc9c8897e4465f85fa6bb38504ab11a5189e71ded47a2ba9309`.
