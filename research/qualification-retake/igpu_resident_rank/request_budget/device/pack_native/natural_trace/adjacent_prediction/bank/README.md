# O que acrescentam quatro previsões ao banco de T1?

**A política conjunta cobre 113 das 375 primeiras leituras CPU.** Guardar as últimas 353 vítimas de T1 cobre 65. A previsão por coocorrência também cobre 65 sozinha, mas 37 são as mesmas chaves no mesmo sítio. Com as ofertas originais a união cobre 93. Consultando o banco antes de escolher quatro leituras, o preditor encontra 48 chaves adicionais e chega a 113. A ablação que usa só frequência chega a 92. São decisões causais reproduzidas nos journals de uma conversa. Os bytes do banco e os da antecipação são hipotéticos. [Protocolo](protocol.md) · [Resultados por braço e chamada](receipt.json)

| Braço | Chaves cobertas | Ranges pedidos ao NVMe | Ranges sem uso na camada/tile | Serviço residual mínimo a 8 GB/s com as janelas do P |
| --- | ---: | ---: | ---: | ---: |
| Sem banco e sem predição | 0 | 0 | 0 | 619,650 ms |
| Banco | 65 | 0 | 0 | 512,244 ms |
| Quatro escolhas por coocorrência | 65 | 576 | 496 | 513,776 ms |
| Banco com as mesmas escolhas | 93 | 576 | 496 | 465,977 ms |
| Banco consultado antes de escolher, frequência | 92 | 576 | 535 | 467,629 ms |
| Banco consultado antes de escolher, coocorrência | 113 | 576 | 514 | 432,929 ms |
| Mesmo banco, até quatro escolhas perfeitas | 315 | 250 | 0 | 147,685 ms |

Os ranges nesta tabela contam só a antecipação, além dos dados de T1 que o banco conserva. A política conjunta pediria 7 615 807 488 B. Sem descontar o tempo das janelas, mesmo o oráculo deixaria 60 chaves por servir, 99,144 ms a 8 GB/s para uma margem de 90,641 ms. Respeitando as janelas o défice aumenta para 57,044 ms. **NO_GO para chegar a 10 s apenas com este banco fixo e quatro buffers por camada, mesmo com previsão perfeita**, nestes custos exteriores. Maior largura, mais antecedência, melhor composição do banco ou ganhos fora destas callbacks têm outro âmbito. A seleção causal precisa de ganhar 342,287 ms noutros componentes mesmo com entrega grátis dos acertos e zero interferência do desperdício. A 4,5 GB/s o seu défice é de 683,837 ms.

Duas execuções iniciais recusaram a ligação ao estudo anterior porque o campo do hash da tabela é acrescentado no momento da exportação. Ambas preservam FAIL. A revisão compara também as 110 linhas reabertas com as linhas calculadas e verifica o próprio SHA do ficheiro. Os dois recibos finais coincidem, SHA-256 `6ddeab1977d1b8013847eb842bdad49befc519178edaf622ef3ff8f55f93daf8`. Duração 2,24/2,29 s, RSS máximo 87 280 KiB. A reprodução usa as mesmas opções da verificação por janela e um novo diretório de saída. [Verificador](score.py) · [Janela e banco com largura ilimitada](../../tier_budget/first_use/previous_layer/bank/README.md)
