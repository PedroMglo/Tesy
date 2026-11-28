# Uma entrega parcial acaba o FFN mais cedo?

Protocolo prospetivo, 28-11-2026. Base desta unidade `44972eaa383fb433c55d6b7e8f5987f739932e97`, árvore `4f11530b41492697ee3ee9cfa4571a56419ce279`, PR #52 sobre #51. Main `293f5b184da9439771cce361cd33fc4068d749f4`. Os contratos de produto continuam em R0 slots40-persistent, ub32, contexto 8192, M3 PARTIAL e M4 NOT_MET.

O primeiro decode C270 à posição 189 na CPU0 fornece a ativação, router, ranks 28/24/8/16, slots 3/14/6/35 e gerações 6/6/5/4. Apenas 24 falta no prestate. O teste de quatro leitores do PR #52 usava quatro faltas para medir a entrega. Aqui o cliente interno espera pelo FFN inteiro. O adversário mais forte já calcula os três hits durante a entrega integral do miss.

## Intervenções e atribuição

Um pedido O_DIRECT ao pack C291 custa 13 221 888 B por braço. Cada braço instala 13 219 200 B de pesos nos mesmos três tensores do slot 14 entre o envio e a barreira. Repor o miss antes de cada braço, preservar os outros 39 slots, quatro workers de serviço e oito threads GGML principais. Relógio monotónico do envio até à soma de quatro ranks por ordem lógica, incluindo cópias, cálculo e conclusão de todos os serviços desse pedido. Arranque, router comum, preparação dos três hits e verificação ficam fora. A amostra tem um único token e camada.

| Braço | Entrega do expert 24 | Cálculo |
|---|---|---|
| FULL | Uma leitura e três cópias | Espera pelos pesos e calcula quatro ranks juntos |
| READY | Idêntica a FULL | Três residentes durante a entrega e depois o frio |
| L32 / E32 | Duas janelas alinhadas entregam 32 linhas de gate e up, duas completam os pesos. Cinco cópias disjuntas | Um dos quatro workers usa um grafo GGML de uma thread para as primeiras 32 linhas até SwiGLU. L32 autoriza-o após entrega completa, E32 após a parcial. A equipa principal executa os residentes, as restantes 2 848 linhas e a projeção down completa |
| LALL / EALL | Uma janela para gate, outra para up e uma terceira para o intervalo em falta de down. Três cópias disjuntas | A equipa principal calcula os residentes e todas as linhas de gate/up até SwiGLU. LALL espera pela entrega completa, EALL só pela publicação de gate/up. O down exige todos os bytes e a ativação real |

Escolhemos o segundo corte pela dependência da projeção down. É uma alternativa determinada antes da observação. Todo o down usa o mesmo MUL_MAT_ID da referência, incluindo a quantização Q8_0 da ativação integral e a ordem completa do produto escalar. Cobrar a materialização de 2 880 F32 para ligar as duas fases. A prioridade da leitura, a granularidade, a sincronização e a afetação das threads pertencem ao candidato. Não alterar o layout em disco nem apropriar um ganho entre famílias. O código estabelece epochs locais, uma publicação parcial e uma final, com registo de início/fim das leituras, das publicações, do trabalho consumidor, de down e da redução. Em falha de leitura acordar os consumidores e terminar a identidade. Uma fixture de falha após publicação parcial deve impedir a conclusão do pedido.

## Critérios congelados

Antes de timing executar os seis braços e comparar os 11 520 F32 ponderados e os 2 880 F32 finais com o target independente. Para cada implementação dividida comparar os 23 040 F32 dos oito estágios do rank frio (gate, up, dois biases, SwiGLU, down, bias e peso). Repetir em todos os braços cronometrados, sempre fora do relógio. Um mutante da ordem da soma tem de ser detetado. Divergência, não finito, OOM, violação de recursos, perda de proveniência ou telemetria encerra a tentativa e preserva o FAIL.

Dois blocos de cinco sextetos, FULL/READY/L32/E32/LALL/EALL e ordem inversa, após o sexteto de paridade. Publicar todas as diferenças emparelhadas. GO_LOCAL por família exige que a mediana das diferenças do candidato contra FULL, READY e a sua ablação seja estritamente positiva nos dois blocos e que a mediana da interseção entre cálculo útil e leitura restante seja positiva em ambos. NO_GO_LOCAL se perder contra READY nas duas ordens ou se a ablação for pelo menos tão rápida nas duas. Os outros resultados são INCONCLUSIVE. O GO_LOCAL admite integração da fronteira no serviço, sujeita a prova de margem no pedido. O NO_GO limita-se a este corte, residência e implementação. Uma reescrita geral exige evidência adicional de uma barreira incontornável do backend atual e benefício no cliente.

## Orçamento e reprodução

Reutilizar os guardas C55, C118 e o manifest de componentes de C270, oito threads CPU, quatro workers, 40 slots por matriz. Build CPU sem CUDA, cap 3 GiB, swap zero e limite 170 s. Janela de recursos fresca antes do operador, cap 4 GiB, swap zero, ≤360 s, ≤1 GiB de leituras lógicas do filho incluindo preparação e controlo negativo, ≤32 MiB de raw por execução. Guardar binário, fontes, identidade da máquina, máximos e recibos num destino privado exclusivo. Modelo inteiro e requests de cliente nesta experiência: zero. A energia fica desconhecida sem medidor.
