# Antecipar experts a partir do token que entra no decode

**NO_GO para atingir 32 passos em 5,333333 s com esta fonte de propostas e o restante trabalho de C295 fixo.** Mesmo disponibilizando gratuitamente todos os experts já usados em ocorrências anteriores do mesmo ID, conservando-os até ao fim e reduzindo as durações dos READ históricos a 80%, faltam 309–362 ms no nominal e 500–504 ms em código. O ID contém informação sobre as primeiras faltas: a cobertura chega a 124/779 no nominal e a 288/928 em código. Essa cobertura já está creditada nos pisos. A decisão abrange os quatro braços fornecidos C294. O caso de código usa os 32/6 s como janela de comparação. M3 PARTIAL e M4 NOT_MET. [Pré-registo](protocol.md) · [Recibo integral](evidence/receipt.json)

Valores em segundos. As cinco primeiras colunas numéricas incluem o restante fixo e usam READ a 0,8×; «marginal» usa o mesmo número de propostas por camada e passo, ordenadas pela frequência anterior de todos os tokens. O par 0/1 limita cada camada a uma proposta. A última coluna volta a cobrar as durações históricas de READ ao reservatório lexical amplo.

| Braço | Sem antecipação | União lexical | Marginal | Lexical 0/1 | Marginal 0/1 | União lexical a 1× |
|---|---:|---:|---:|---:|---:|---:|
| Nominal 2 | 6,22346 | 5,64257 | 6,19309 | 6,15752 | 6,22346 | 6,60986 |
| Nominal 3 | 6,27783 | 5,69520 | 6,24473 | 6,20689 | 6,27783 | 6,66127 |
| Código 2 | 7,29154 | 5,83320 | 7,18888 | 7,10138 | 7,29005 | 6,83722 |
| Código 3 | 7,30308 | 5,83767 | 7,19950 | 7,11036 | 7,30128 | 6,83983 |

### Origem e momento das escolhas

O cliente C294 consome o vetor C276 de 2 197 ou 2 105 IDs de entrada e depois chama o target uma vez por elemento de `continuation_ids` (32). Cada seleção lexical conhece apenas o ID que entra nesse passo. O histórico antes do primeiro decode inclui 2 044/1 952 posições do prefixo e as 153 incrementais. O WRT40 qualificado fornece 76 904/73 684 linhas de ranks antes do decode nas duas entradas. As camadas 0–34 têm uma linha por posição; a camada final só executou a última linha de cada uma das nove chamadas. Cada forward fornece à tabela os ranks para o passo seguinte. 18/32 IDs nominais e 24/32 dos de código tinham ocorrido antes do respetivo passo. O replay confere I drenado, P/F, os 4 608 ranks ordenados por braço, a primeira geração ausente e suas três leituras. As duas réplicas partilham os IDs e as rotas de cada entrada. [Cliente C294](../../../tools/expert_service_window.cpp) · [Autenticação dos inputs e das rotas](../warm_route_family/grade.py) · [Controlo de primeiras faltas](../primary_backing/README.md)

### Custo e alcance

A união lexical nominal emite 4 024 propostas. Com I e a retenção gratuita, há 323 ingressos novos (244 CPU e 79 CUDA). Servem uma primeira procura no mesmo passo em 87 casos e num passo posterior em 37; os 199 restantes ficam sem consumidor até ao fim. Em código são 4 763 propostas, 543 ingressos (430 CPU e 113 CUDA), com 198 usos no mesmo passo, 90 posteriores e 255 sem uso. As propostas marginais amplas cobrem apenas 10 e 28 primeiras faltas. A regra lexical 0/1 cobre 16 e 55, contra 1 e 2 na sua ablação marginal. A materialização de todos os ingressos da união lexical pediria 4 269 801 600/7 178 025 600 B de payload antecipado somando os dois tiers. Incluindo a procura residual, sobe para 12 928 377 600/15 638 313 600 B. São bytes lógicos para a política ampla no reservatório ideal; uma política que só admita um subconjunto pode evitar parte desses ingressos. [Contadores por tier e por braço](evidence/receipt.json)

O piso conserva a ordem causal dos grupos e a duração das leituras restantes. Toda proposta já disponível pode evitar uma primeira falta mesmo que o consumidor só apareça vários passos depois. As propostas são gratuitas desde a entrada do próprio token e qualquer procura primária fica retida de graça daí em diante. Nestas condições, o conjunto disponível contém o de qualquer seleção da mesma família. O READ puro da união, a 0,8×, dá 3,869/3,864 s no nominal e 4,016/4,009 s em código. Mesmo a 1×, o READ isolado cabe na janela. O fecho depende, portanto, de preservar o restante trabalho de C295. Para o mesmo restante e a mesma cobertura, o fator máximo admissível sobre as cadeias de READ residuais é 0,7361/0,7251 no nominal e 0,7004/0,6994 em código. Uma redução demonstrada deste serviço, outra fonte que antecipe chaves fora da união, ou a possibilidade de ocultar trabalho residual constituem premissas de reabertura. Os pisos deixam por qualificar o custo dos quatro workers, contenção, cópias, ocupação e reposição, o primeiro conteúdo final e a conversa natural. [Definição do custo fixo](../primary_backing/protocol.md)

### Reprodução

Uma família offline no commit `862c36c7b9ff5a8f83baf88a9c87ccd1acb91598`, árvore `4886ac463c46dbe9c17808ca97027e3ed0daf218`. Em 2,66 s de parede, 2,44 s de CPU de utilizador e 0,17 s de sistema, o processo atingiu 108 820 KiB de RSS. Os quatro testes sem modelo cobrem atualização posterior ao passo, poda final, seleção marginal, retenção entre passos e a última leitura de cada grupo. O recibo de 49 426 B tem SHA-256 `1e30c76c18f5722438bcec523ff92614183bc1811cf46880411d5af2692a9e5a`. O ensaio não abriu pesos nem usou GPU.

```sh
s=research/qualification-retake/lexical_decode
python3 -B -m unittest discover -s "$s"
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B "$s/screen.py" --fixture "$C276/development-inputs.json" \
  --family "$WRT_FAMILY" --raw-dir "$TESY_C294_RAW" --new-output-dir "$DESTINO_NOVO"
```
