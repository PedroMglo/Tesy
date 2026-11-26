# Captação de vítimas apenas a partir de T2

**NO_GO nos dois preços de serviço congelados.** Uma L2 fria de 353 slots preservaria 280 das 1091 leituras de decode (25,66%), ultrapassando as 219 exigidas no crivo de hits. Mas nenhuma das 875 primeiras procuras obrigatórias até ao primeiro conteúdo final pôde receber bytes de uma vítima anterior de T2. Nas 441 waves correspondentes, cada chave estava ausente à entrada e a reserva identificada era a primeira da chave no pedido. Com o resto fixo de 5,996896 s, persistem pisos de **12,228464 s** aos preços observados e **10,982150 s** a 0,8×. Uma leitura evitada noutro ponto do pedido contribui para a contagem de hits; a sua contribuição ao primeiro conteúdo final exigiria uma dependência identificada. [Protocolo](protocol.md) · [Recibo por fase e tier](receipt.json)

| Slots adicionais | Hits de prefill / 1263 | Hits de decode / 1091 | Retornos do FD restantes até ao fim do prefill | Vítimas CPU→RAM em T2 | Vítimas CUDA→RAM em T2 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0, R0 | 0 | 0 | 16 711 176 192 B | 0 | 0 |
| 239 | 195 | 198 | 14 131 093 504 B | 20 727 705 600 B | 9 861 523 200 B |
| 353 | 237 | 280 | 13 575 352 320 B | 20 251 814 400 B | 9 650 016 000 B |
| 4608, universo completo | 411 | 779 | 11 273 060 352 B | 15 479 683 200 B | 7 640 697 600 B |

O cenário de 4,5 GB/s concede 10 938 366 806 B para 47 saídas e 11 688 366 807 B para a sensibilidade de 46 avaliações. Após dar crédito à primeira expulsão dos residentes existentes, persistem 852 chaves inicialmente ausentes e **11 262 758 400 B** de payload obrigatório no prefill. O défice da linha de 47 exige pelo menos 25 chaves exteriores à entrada preparadas em T1. O piso de volume cabe na linha de 46, embora a condição de tempo falhe. No cenário anterior, em que só a publicação alimentava a cache, 199 residentes expulsos também tinham de ser relidos uma vez. Esta diferença de elegibilidade impede transportar os mínimos conjuntos dessa outra política. [L2 por publicação](../host_cache/README.md) · [Oráculo conjunto daquela política](../warm_oracle/joint.md)

**TRACE_DERIVED.** Manteve-se a agenda primária R0 e considerou-se cada cópia de vítima disponível antes de reutilizar o slot, sem cobrar tempo pela cópia. O recibo também conta entrega por hit, SET do primário e inserções sem reutilização. O cenário de 353 entradas cabe na estimativa de RAM pré-registada. O diagnóstico cobre um pedido natural nominal e a sua trajetória. Os bytes contabilizados não medem tempo de transferência ou disponibilidade de uma cópia em T1.

Protocolo e programa em `7201ee01`. Três testes incluem pin, ordem sem promoção no hit, cópia da vítima original e rejeição de uma falsa primeira procura. Os planos privados R01/R02 deram recibos idênticos por SHA-256 `1edac104fb4a96482cabd1ad35deb357e49a1823bc8a814f26149affd5aa7aa9`. Cada reprodução durou 0,20 s, com 47 036 e 47 144 KiB de RSS. Nenhum peso ou GPU foi utilizado.

```sh
STUDY=research/qualification-retake/phase_fd/integrated/t2_victims
python3 -IB "$STUDY/test_screen.py"
timeout 120s prlimit --as=536870912 --cpu=120 --fsize=1048576 -- \
  python3 -IB "$STUDY/screen.py" --plan-dir "$PLAN" \
  --on-dir "$ON" --off-dir "$OFF" --new-output-dir "$NOVO"
cmp "$NOVO/receipt.json" "$STUDY/receipt.json"
```
