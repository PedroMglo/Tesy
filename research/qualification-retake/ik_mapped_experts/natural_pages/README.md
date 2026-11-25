# A escolha do ticket nas quatro tiles de 32 do nominal

**GO para verificar a ordem dos tickets e a topologia das splits no ik.** No T2 real, os quatro experts escolhidos em cada camada variam entre posições. A seleção dos IDs efetivos exigiria conjuntos de 4,631 a 8,917 GB de páginas das três matrizes por tile de 32. Se o ticket integral vencesse nos 35 sítios elegíveis de cada tile, o conjunto seria de **59,222 GB por tile**, ou 55,155 GiB. Este conjunto ultrapassa 2,75 vezes o cap de 20 GiB de RAM mesmo concedendo toda a memória às páginas de pesos. As camadas executam-se em sequência e só algumas splits podem estar adiantadas. Nenhum desses conjuntos precisa de estar residente simultaneamente. [Protocolo prévio](protocol.md) · [Recibo completo](result.json)

Os journals das partes 97 e 106 concordam nos 7 012 quartetos ordenados, nas suas posições, nos 1 440 bindings iniciais e na colocação do Tesy. Os 28 048 ranks incluem repetições. Cada endereço provém do tensor MXFP4 original no C283, com stride de 4 406 400 B por papel. A soma abaixo é em GB decimais de páginas de 4 096 B, deduplicadas dentro de cada tile. As duas colunas de tier usam as 25 camadas CPU e as 11 CUDA do Tesy para localizar a procura. A colocação e as ordens de tickets efetivas do ik continuam por observar.

| Chamada e tile | Linhas de entrada | Pares camada/expert distintos | Seleção CPU | Seleção CUDA | Seleção total | Integral quando elegível |
|---|---:|---:|---:|---:|---:|---:|
| 1 · 1 | 5 | 459 | 4,512 | 1,561 | 6,073 | 6,073 |
| 2 · 1 | 32 | 674 | 5,808 | 3,109 | 8,917 | 59,222 |
| 2 · 2 | 32 | 350 | 3,003 | 1,627 | 4,631 | 59,222 |
| 2 · 3 | 32 | 567 | 4,287 | 3,215 | 7,501 | 59,222 |
| 2 · 4 | 32 | 594 | 4,498 | 3,360 | 7,858 | 59,222 |
| 2 · 5 | 20 | 1 182 | 11,535 | 4,101 | 15,635 | 15,635 |
| 3 · primeiro decode | 1 | 144 | 1,323 | 0,582 | 1,905 | 1,905 |

A tile de 20 tem o maior conjunto seletivo. Das quatro tiles de 32 resultam 140 oportunidades teóricas de população integral. Em cada uma, as 25 camadas do estrato CPU contribuem 42,302 GB e dez camadas do estrato CUDA 16,921 GB. A camada 35 tem zero linhas na chamada de 5 e nas quatro primeiras tiles de 32, uma única linha na última tile de 20 e uma em cada passo de decode. O limiar aplica-se às linhas do tensor de IDs. O teste nativo também separa a receção do primeiro ticket na época de uma duplicação posterior. [Fixture do pin](../protocol.md)

| Fase | Soma por tile, seletiva / integral elegível (GB) | União ao longo da fase, seletiva / integral elegível (GB) |
|---|---:|---:|
| Prefill 5+148 | 50,615 / 258,598 | 23,159 / 59,275 |
| 46 passos de decode | 87,644 / 87,644 | 24,363 / 24,363 |
| T2 | 138,259 / 346,242 | 32,665 / 59,844 |

Na seleção, a interseção entre páginas do prefill e do decode é de 14,858 GB. Se o integral vencer em todos os sítios elegíveis, passa a 23,795 GB. A soma dos chunks seletivos de decode já arredondados a páginas totaliza 87,807 GB, acima dos 87,644 GB deduplicados por passo. O recibo distingue também o payload codificado. Nenhum destes valores mede chamadas ao armazenamento, estado inicial da cache Linux, expulsões durante a conversa, tráfego PCIe ou tempo. As 47 saídas naturais só exigiram 46 chamadas de decode. A atribuição dos 40 slots de R0 autentica o pedido de referência e não fornece uma imagem da cache Linux. [Cadeia de referência](../../igpu_resident_rank/request_budget/device/pack_native/natural_trace/prefill_retention/README.md)

O discriminante seguinte é um mapa do scheduler no pin `7a5d9000`, para as formas 1/5/20/32. Precisa de identificar as splits de cada MMID, as linhas e a identidade dos IDs finais, o backing dos três pesos originais, a época e se o primeiro ticket foi seletivo ou integral. A ablação `GGML_MOE_PREFETCH_AHEAD=0` retira a antecipação integral. Ficam para observação posterior as faltas de página, as leituras físicas e a exatidão do target no frontend escolhido. [Condições no scheduler](../loader.md)

## Reprodução sem modelo

Método congelado em `1f90d5ee`, protocolo em `e388e6cd`. R01 usou os dois originais em `/var/tmp`, R02 reabriu as partes 97 e 106. Cada execução produziu 194 229 B em `/tmp/tesy-ik-natural-pages-20261125-r0{1,2}`. Os três ficheiros de R01 e R02 são byte a byte iguais. `sites.tsv` cobre as 1 872 combinações camada/tile, incluindo a poda. `tiles.json` conserva os dois cenários, os tiers e cada uma das 52 tiles. O recibo sela ambos com SHA-256 e tem o digest `2f776eaab50c31abda982dd1b0d946bfaacf3916b8ce259a367b75acb0f59a5f`. Dois testes sem dados privados cobrem os ranks repetidos, páginas em fronteiras de chunks, reuso, ID inválido e o caso de uma camada podada numa tile de 32. [Verificador](score.py) · [Testes](test_score.py)

Executar a partir da raiz Tesy, fornecendo um destino que ainda não exista.

```sh
module=research/qualification-retake/ik_mapped_experts/natural_pages
archive=/mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01
inventory=/mnt/sdisk-ssd-ext/Tesy/repo/c7-native-placement-screen-20260927-1117utc/results/c283-exact-expert-service-epoch-20261006T194311Z/build/model-tensor-metadata.jsonl
python3 -IB -m unittest discover -s "$module"
prlimit --as=1073741824 --cpu=300 -- python3 -IB "$module/score.py" \
  --p97 "$archive/part-97/tesy-c281-pack-observer-natural-20261125-r01" \
  --p106 "$archive/part-106/tesy-full-prefix-natural-physical-20261125-r01" \
  --inventory "$inventory" --new-output-dir "$new_output_dir"
```
