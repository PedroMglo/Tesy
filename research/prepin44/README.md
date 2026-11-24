# Pré-proteção da wave corrente no nominal C163 de 44 slots

**GO para a hipótese de reduzir as leituras lógicas no perfil diagnóstico.** No prefill 5+148 de cada braço nominal C163-ON, a pré-proteção reduz de 901 para 851 as admissões. Os dois braços ON e as duas regras de serviço reproduzem o mesmo número de admissões. Os snapshots iniciais e as rotas são de 44 slots. No modelo com serviço retido e trabalho fora de WAIT fixos, o teto de ganho é 0,653145 s / 0,660163 s perante cortes de 0,905953 s / 0,905890 s. **NO_GO para 10% por esta via.** A latência física, a paridade numérica e o produto de 40 slots continuam por demonstrar. [Pré-registo](protocol.md) · [Resultados emparelhados](paired-evidence/receipt.json) · [Tempo](time.md) · [Continuação com a cache natural](isomorphism.md) · [Limiar para reabrir a hipótese](margin.md)

| C163, em ambos os braços e ordens | CPU | CUDA0 |
|---|---:|---:|
| Admissões R0 / pré-proteção | 649 / 620 | 252 / 231 |
| Leituras evitadas antes de restauração | 29 | 21 |
| Slots com ocupante diferente após prefill | 73 | 49 |
| Ciclos na permutação | 23 | 15 |
| Restauração sem slot intermediária, leituras / cópias locais | 23 / 50 | 15 / 34 |
| Leituras líquidas evitadas por esse plano | 6 | 6 |
| Restauração com scratch, leituras / cópias locais | 0 / 96 | 0 / 64 |
| Primeiro decode original e candidato, hits / misses | 88 / 12 | 41 / 3 |

Cada expert tem 13 219 200 B. As 50 admissões evitadas pertencem à chamada de 148. Nenhum expert tem mais admissões no total da sua chamada. A restauração sem slot intermediária relê um expert por ciclo e copia os restantes. Retém 158 630 400 B de leitura GGUF evitada e movimenta 1 110 412 800 B de payload em cópias locais (2 220 825 600 B entre leitura e escrita). A alternativa com scratch conserva 660 960 000 B de leitura GGUF evitada, paga 2 115 072 000 B de cópias locais e requer até 13 219 200 B de workspace por tier nesta fixture. Os planos verificam as identidades simbólicas de gate/up/down por slot. A leitura física de NVMe, o custo de PCIe/VRAM, os valores de ativação e as durações das cópias e da coordenação continuam desconhecidos. Os dois planos fornecem custos construtivos. Não provam o custo mínimo global de reconstituição.

A pertença aos conjuntos residentes de cada camada coincide. O candidato altera 67 contadores de geração de slot, 876 carimbos de último uso e vários vetores de parking/keep. No corte drenado, o comparador de restauração assume acesso ao estado de uma sombra R0 independente, cobra as movimentações acima e restaura os campos que diferem, incluindo a diferença de 50 em next_work_id. O primeiro decode tem os mesmos hits e misses sem reconstituir a disposição física. Depois de reconstituição, o simulador também verifica todos os campos de camada, as reservas e o contador global desse decode. Na call 11 observada, o cliente fornece a primeira continuação; esse replay demonstra uma resposta da cache condicionada às rotas fornecidas.

## Agenda e limite da prova

R0 e candidato partem do mesmo before-warm.snap e usam a mesma regra FIFO nas quatro workers. EARLY termina o serviço pendente logo que o callback liberta o mutex. LATE começa por satisfazer a última dependência ainda em falta e adia a conclusão de preloads desnecessários à barreira. Os tickets são despachados por ordem FIFO em ambos. O identificador de quem publica primeiro, os tickets stale e as esperas podem divergir. Houve zero tickets stale com EARLY e 277 com LATE em ambos os braços simulados. Os dois R0 reproduziram todas as 901 reservas e seus destinos/gerações, os vetores após prefill e as 15 reservas históricas da primeira chamada unitária. A reprodução do baseline com as completações realmente observadas precede as simulações.

Qualquer ordem possível entre estas completações conserva as admissões lógicas deste caso. Uma rota começa sem cargas pendentes. A reserva e a emissão de um callback só permitem participação dos workers quando a barreira liberta o mutex. A política completa o mapa dos experts da próxima wave, facto verificado após cada passagem. Por indução, na próxima wave todos os experts já têm slot. READY e LOADING podem mudar uma promoção, mantendo a identidade do slot. Todos ficam protegidos antes de qualquer vítima de preload, e todas as cargas em voo são precisamente desses slots. A reserva de cada preload fixa de imediato o respetivo keep. Assim a comparação por hotness, LRU e índice físico vê sempre os mesmos candidatos em cada política. Uma etapa terminal consome o que ainda estava a carregar. A fixture verifica os pressupostos em cada camada. O argumento deixa abertos a duração dos serviços e o caminho crítico.

Proveniência e custo desta unidade. O hash do controlador está no pré-registo e no recibo. O leitor integrado da unidade-base tem SHA cfea049ef5b61c1b9ac73495a219db9d7e9e581a32cd030cd6f00bd7ad976949. A única diferença face à versão congelada é uma linha em branco entre imports. Os dois braços verificam o manifesto de todos os inputs através desse leitor. A corrida de controlo consumiu 1,10 s, e as duas corridas emparelhadas 1,53 s e 1,54 s. Pico de 84 296 KiB. Sete fixtures unitárias passaram em 0,06 s. Pesos e GPU zero, energia por medir, nenhum holdout. Estes números são a despesa do simulador. [Critérios e orçamento](protocol.md)

Comandos a partir da raiz, adotando o nome desta pasta para P. O nome da saída tem de estar livre.

```bash
P=research/prepin44
B=research/prefill44-replay
PYTHONPATH="$B:tools:$P" python3 -B -m unittest discover -s "$P"
python3 "$P/compare.py" --replay-dir "$B" --repo . --raw-dir "$TESY_C163_RAW" --new-output-dir "$OUT"
```


## Decisão da unidade

A rota causal consegue evitar as 50 cargas da chamada de 148 e servir as 47 chamadas de decode fornecidas conservando os seus próprios slots. Ritmo de decode do produto, energia, logits e latência de uma implementação física continuam NOT_RUN. O R0 operacional usa 40 slots, M3 PARTIAL e M4 NOT_MET.

Para justificar maior investimento nesta política, a observação discriminante é uma redução do serviço das cargas **retidas** nos intervalos que condicionam a última wave, ou do trabalho nas partes do callback que o journal não delimita. Usando redução uniforme, o teto só chega ao corte nos dois braços a partir de 5,1494% nos serviços retidos. Aplicar o melhor tempo observado entre ON-1 e ON-2 a cada uma das 851 identidades ainda falha o corte nos dois braços. Uma redução não uniforme concentrada num serviço crítico exigiria recalcular os intervalos. A economia isolada de 50 em 901 admissões fica abaixo do corte de latência neste regime. [Sensibilidade e margem](margin.md)

A branch da comparação parte do controlador independente `4b84188d577d8e1415ec216765aaf1fd82060757` do PR #46, da main observada `293f5b184da9439771cce361cd33fc4068d749f4`. O PR #45 contém a análise separada do servidor de 40 slots e o #44 a auditoria dos workers de decode. Cada screen tem pré-registo, saída exclusiva e recibo. As reproduções finais locais da comparação, dos limites temporais e das 47 chamadas demoraram 1,56 / 1,67 / 2,28 s e coincidiram byte a byte com os recibos da unidade. Energia sem instrumentação. Nenhuma alteração ao launcher ou ao backend.
