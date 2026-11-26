# Dividir os quatro ranks entre CPU e 64 experts fixos em GPU

**NO_GO para atingir 6 passos/s nos quatro braços C294 por esta via.** O nominal parece viável se a presença de um único peso na GPU apagar toda a camada. Quando se conserva o trabalho até à entrega do router e o serviço de apenas um dos misses CPU que ficaram por promover, até a escolha ideal de 64 chaves deixa pelo menos **8,219–8,258 s no nominal** e **9,780–9,781 s em código**. A meta dos 32 passos exige até 5,333 s. Estes pisos continuam a conceder execução e transferências gratuitas aos ranks promovidos. [Protocolo prospetivo](protocol.md) · [Recibo por braço](replay-r2/receipt.json)

| C294 trace-ON | Decode, janela do journal | Teto A, ganho permitido | Testemunha A, ganho no cenário gratuito | Teto B, ganho permitido | Piso B restante | Teto B (passos/s) |
|---|---:|---:|---:|---:|---:|---:|
| nominal153 #2 | 9,381 s | 4,494 s | 4,452 s | 1,162 s | 8,219 s | 3,893 |
| nominal153 #3 | 9,415 s | 4,505 s | 4,459 s | 1,157 s | 8,258 s | 3,875 |
| code153 #2 | 10,986 s | 5,298 s | 5,270 s | 1,206 s | 9,780 s | 3,272 |
| code153 #3 | 11,010 s | 5,281 s | 5,251 s | 1,228 s | 9,781 s | 3,272 |

Em A, basta que uma chave (camada, expert) pertença ao conjunto estático para apagar o intervalo entre a ativação da camada CPU e a fronteira da seguinte. A testemunha gulosa de cada braço conhece os pesos temporais de todos os passos futuros. No nominal, ela deixa 4,929 e 4,956 s fictícios. Em código, mesmo o teto certificado deixa 5,688 e 5,729 s. Os conjuntos e a ordem dos 4 608 ranks provêm dos mesmos quatro braços da análise anterior; cada braço recebeu o seu próprio orçamento otimista de 64 cópias. [Identidades e capacidade](../gpu_cohorts/README.md)

Em B, o primeiro instante de despacho passa a ser o router autoritativo. Se algum rank for promovido, o FFN ainda precisa dos três componentes originais de **cada** miss não promovido. Cada componente tem 4 406 400 B. Na janela de cada camada e passo conservámos apenas a maior cadeia serial desses três READ de um expert, permitindo toda a sobreposição entre os outros workers. Das 3 200 seleções CPU por braço, no nominal 762 estavam ausentes e 2 438 residentes; em código foram 927 e 2 273. Não ocorreram seleções em LOADING. Para cada geração o enqueue segue o router da própria call, os READ e SET de cada componente pertencem ao mesmo slot e geração, e o commit antecede a próxima fronteira. O crédito por quantização dos relógios é favorável ao candidato. O resto da execução GPU, CPU, mistura e coordenação recebe custo zero nas janelas elegíveis. Este cálculo mantém os tempos de READ dos misses que ficam no CPU e os tempos dos intervalos não tocados.

**Como verificar o teto.** Cada grupo tem quatro chaves e um custo w. O indicador de que pelo menos uma das quatro está promovida é limitado tanto por 1 como pela soma das quatro escolhas. Para qualquer preço inteiro p entre zero e w, atribuímos w−p ao termo fixo e p a cada chave do grupo, e somamos apenas os 64 maiores scores por chave. Em B, se as durações obrigatórias ordenadas forem d₁≥…≥d₄, remover d₁−d₂ requer promover o primeiro rank dessa ordem; remover d₂−d₃ requer promover os dois primeiros, e assim sucessivamente. A conjunção dos j primeiros é no máximo a soma das suas escolhas dividida por j. O verificador aplica ambas as desigualdades em inteiros de 1/12 µs, sem presumir que a busca de preços encontrou um ótimo. Um segundo cálculo verifica o certificado publicado. As listas de preços seguem ordem de call e camada; as listas de chaves-testemunha usam `128×camada + expert`. [Preços duais por grupo](replay-r2/prices.json) · [Implementação e teste por enumeração exaustiva](screen.py)

Uma fixture física de um rank não consegue alterar esta decisão no regime congelado. Continua em aberto se uma subdivisão poderia melhorar modestamente o custo ou se uma mudança de serviço, de cache dinâmica ou de memória disponível permitiria outro regime. M3, M4 e os tempos da conversa natural continuam com os respetivos contratos.

### Reprodução

```sh
LC_ALL=C python3 -B research/qualification-retake/partial_gpu_rank/screen.py \
  --raw-dir "$TESY_C294_RAW" --new-output-dir "$DESTINO_NOVO"
```

Primeira execução em 1,82 s e 37 628 KiB de RSS. A reprodução em 1,80 s e 38 396 KiB repetiu todos os campos científicos e acrescentou os preços auditáveis. Recibo SHA-256 `67450234d75d37d41c0b5e66397607612a5911c48afd1b4b12cedcbe64a890ac`, preços `6ab950226d317eff758de153b13b80324510505285873aeed85200801d808181`. A enumeração da fixture para seis capacidades e o Ruff passaram. Zero pesos, GPU, forwards ou Actions.
