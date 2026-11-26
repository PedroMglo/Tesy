# O efeito conjunto da política e da capacidade do banco GPU

**Com 161 slots, ClassLRU evitou 539 das 8 675 reposições de LRU no segundo
turno, equivalentes a 7,125 GB de pesos.** A frequência acumulada no primeiro
turno ajudou sobretudo no prefill de T2. Com 128 slots, a mudança de política
evitou 1 923 reposições em T2. Decisão **GO para comparar as duas políticas
na mesma capacidade no ik, condicionado à qualificação numérica e de recursos**.
A latência do cliente continua **INCONCLUSIVE**. O resultado é TRACE_DERIVED
para as rotas do Tesy. [Protocolo](protocol.md) · [Resultados](result.json)

| Fills do banco de pesos | LRU 128 | ClassLRU 128 | LRU 161 | ClassLRU 161 |
|---|---:|---:|---:|---:|
| T1 prefill, 2 043 posições | 21 081 | 21 016 | 21 081 | 20 814 |
| T1 decode, 77 avaliações | 11 088 | 8 523 | 7 959 | 8 048 |
| T2 prefill, 5 + 148 | 3 826 | 3 497 | 3 818 | 3 430 |
| T2 até à primeira peça final | 10 162 | 8 317 | 8 484 | 7 930 |
| T2 decode, 46 avaliações | 6 624 | 5 030 | 4 857 | 4 706 |
| T2 completo, 10 450 procuras únicas por sítio | 10 450 | 8 527 | 8 675 | 8 136 |
| Dois turnos, 42 619 procuras únicas por sítio | 42 619 | 38 066 | 37 715 | 36 998 |
| Payload dos dois turnos (GB decimais) | 563,389 | 503,202 | 498,562 | 489,084 |

**Combinação.** Partindo de LRU 128, aumentar a capacidade primeiro poupa
1 775 fills em T2. Mudar depois a política com 161 poupa mais 539. Pela ordem
inversa, a política poupa 1 923 e a capacidade mais 391. O resultado comum
são **2 314 fills, 30 589 228 800 B**, com mais 436 233 600 B de pesos
residentes para os 33 slots. Somar os dois efeitos medidos isoladamente na
base 128 contaria 1 384 fills duas vezes. Cada fill carrega três matrizes
de 4 406 400 B. As contagens de payload excluem a guarda, biases, tráfego de
protocolo e eventuais releituras da origem no page cache. [Controlo de LRU](../README.md)

**Variação por fase.** Em 161 slots, os 388 fills evitados no prefill e 151
no decode perfazem os 539 de T2. Nos 1 656 sítios de decode, ClassLRU venceu
em 346, perdeu em 225 e empatou nos restantes 1 085. No decode anterior de T1
carregou mais 89 que LRU, compensados por menos 267 no prefill desse turno.
O aquecimento custa 381,533 GB de payload para ClassLRU 161, face a 383,886 GB
em LRU 161. Em T2, a call de cinco e as cinco tiles seguintes custam
381, 579, 308, 512, 527 e 1 123 fills com ClassLRU 161.

| Transferência útil exigida no segundo turno | LRU 128 | ClassLRU 128 | LRU 161 | ClassLRU 161 |
|---|---:|---:|---:|---:|
| Até à primeira peça em 10 s (GB/s) | 13,433 | 10,994 | 11,215 | 10,483 |
| Decode, 47 tokens em 47/6 s (GB/s) | 11,178 | 8,488 | 8,196 | 7,942 |

Na configuração ClassLRU 161, as 7 930 reposições até à primeira peça requerem
104,828 GB. Conceder 16 GB/s úteis durante toda a transferência deixa 3,448 s
para o restante trabalho em série até essa peça. No decode, 62,210 GB deixam
3,945 s. A taxa de 16 GB/s é um teto bruto otimista. Se os dois planners
obtiverem a mesma taxa útil serial B, o custo de gestão adicional admissível
de ClassLRU 161 face a LRU 161 é inferior a 7 323 436 800/B segundos até à
peça e a 1 996 099 200/B segundos no decode. A 16 GB/s são 457,715 ms e
124,756 ms. Sobreposição ou custos de serviço diferentes exigem uma medição
do caminho crítico. [Fonte do teto](../../../../stock_link/README.md)

**Limites da identificação.** O observador C281 abriu imediatamente antes
do primeiro POST. Nesse instante viu 261 slots READY e 1 179 vazios do
Tesy. A história da sonda anterior ficou fora do journal. Os quatro braços
começam com o banco e os contadores do ik vazios por hipótese. Preservam
todas as 74 278 linhas T1, o corte entre POSTs e as 7 012 de T2, com a
podagem da última camada. O mesmo objeto de política processa ambos os
turnos. A LRU reproduziu em todos os 46 passos de decode a conclusão anterior
para qualquer entrada. No ClassLRU, o histórico de frequências anterior ao
primeiro POST poderia alterar vítimas. A colocação conjunta das 36 camadas
e os IDs do ik precisam de confirmação no próprio target. O último evento
do cliente e o quarto rank de cada token foram conservados de acordo com
o revisor anterior. [Captura dos dois turnos](../../../../igpu_resident_rank/request_budget/device/pack_native/full_prefix/protocol.md)

No pin 7a5d9000, o hook de ClassLRU recupera a geometria real de selected e
o planner incrementa o relógio de cada camada pelo número de linhas. Cada
chave distinta é atualizada uma vez por sítio. LRU usa n_tokens=1 no mesmo
hook. O verificador chama estes métodos do header original e confere a
conservação de hits/fills/evictions, as chaves e os mapas inversos em cada
sítio. O antecedente de seis planos confirmou o operador numa geometria
pequena. [Hook](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama-moe-cache.cpp#L758-L770) · [Planner](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama-moe-cache-policy.h#L262-L317) · [Fixture anterior](../../../../stock_operator/README.md)

Reprodução sem pesos, GPU ou servidor, a partir desta pasta, com diretórios
novos em cada execução. A build foi selada em c75ba9db após o protocolo
c6278d63. Os originais e as cópias das partes 97/106 produziram o mesmo
receipt.json SHA-256 `bc03d6648dfa4103a44648ba6d052089042309e813f3ea732fa29384e3d52870`.

```sh
python3 -m pytest -q test_score.py
python3 -IB score.py build --ik "$IK" --lib "$GGML_R03" --new-output "$BUILD"
python3 -IB score.py study --p97 "$P97" --p106 "$P106" --build-dir "$BUILD" \
  --build-sha256 "$(sha256sum "$BUILD/receipt.json" | cut -d' ' -f1)" --new-output "$OUTPUT"
```
