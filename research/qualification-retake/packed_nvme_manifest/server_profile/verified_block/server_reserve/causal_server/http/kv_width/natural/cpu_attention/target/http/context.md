# Um contexto adicional muda os blocos e o seu preço

**INCONCLUSIVE para um ganho líquido do filtro. NO_GO como solução isolada para os 10 s no modelo de custos congelado.** A regra copia a mesma continuação do último bigrama apenas quando coincide também o token anterior. O replay conserva todos os IDs das duas respostas. T2 passa de cinco rejeições imediatas para uma. Cinco dos sete blocos novos em T2 carecem de preço e todas as verificações de T1 mudam de posição. O prefill que antecede o primeiro conteúdo final continua exposto. [Protocolo anterior ao replay](context-protocol.md) · [Resultados](context-result.json) · [Quatro referências físicas](family.md)

| Turno | Política | Passos seriais | Verificações | Aceitação de 0 / 1 / 2 | Tokens propostos / aceites |
|---|---|---:|---:|---:|---:|
| T1 | Fixa | 57 | 9 | 2 / 3 / 4 | 18 / 11 |
| T1 | Três tokens de contexto | 62 | 7 | 3 / 0 / 4 | 14 / 8 |
| T2 | Fixa | 23 | 11 | 5 / 0 / 6 | 22 / 12 |
| T2 | Três tokens de contexto | 30 | 7 | 1 / 3 / 3 | 14 / 9 |

Os custos abaixo mantêm o preço de cada passo serial do OFF e atribuem custo medido de ON apenas a uma verificação idêntica nas mesmas posições. Um grupo com custo novo recebe zero no cenário favorável. Lookup, coordenação e diferenças de residência consomem o saldo se ficarem expostos. A conta usa os mesmos dados de OFF nas duas colunas. São preços condicionais de duas observações ON e uma referência serial.

| T2, 47 saídas | Preços do primeiro ON | Preços do segundo ON |
|---|---:|---:|
| Decode com cinco blocos inéditos gratuitos | 6,975 s | 7,006 s |
| Custo novo total admissível para 6 tok/s | 0,858 s | 0,828 s |
| Custo novo total admissível para empatar o decode de OFF | 2,137 s | 2,107 s |
| Primeiro conteúdo final com os cinco gratuitos | 16,917 s | 16,948 s |
| Prefill máximo compatível com 10 s nesse cenário | 3,129 s | 3,099 s |

Em T1, para proteger o tempo de decode e o primeiro final, os sete grupos e a mudança de residência dispõem em conjunto de 3,925 s sobre o OFF. A observação mínima que preço e correção exigem em T2 são os cinco despachos inéditos com o estado produzido pelo próprio filtro, responsáveis pelas posições 11, 16, 19, 37 e 41 no índice de saídas já confirmadas. Três têm aceitação parcial e dois completa. A passagem de custo entre despachos exige conservar os pools no histórico real. A prioridade passa ao prefill porque mesmo o cenário favorável falha a latência de T2 em mais de 6,9 s. A regra permanece candidata a ganho parcial se uma medição vier a mostrar margem. [Implementação](context_filter.py) · [Próximo teste sobre as leituras do prefill](io-protocol.md)

Os cinco controlos sem modelo confirmaram contexto favorável, contexto divergente, escolha da ocorrência mais recente, história insuficiente e limite do pedido. Duas tentativas com limite de 256 MiB de espaço de endereços terminaram nos imports, antes de ler os dados. A importação ocupava 278 180 KiB virtuais e 42 560 KiB de RSS. As duas execuções seguintes usaram cgroups com o mesmo orçamento de 256 MiB de RAM e swap zero, demoraram 0,56 / 0,55 s e atingiram 39,1 / 39,2 MiB de pico no cgroup. O invólucro zsh falhou ao guardar o código de saída depois dos dois processos. Os logs do systemd confirmam saída zero de ambos e as duas cópias do resultado têm SHA-256 `7b4be853003d9c52c84f11c2b7e6ac846842893e7424be7b0255d49c0d3e420d`. Pesos, GPU e pedidos novos zero. [Manifesto privado](../../../../../../../../../../../private_archive/part-186.json)

Para reproduzir, usar o commit `f060ae2ac0de2b09773ccf515bb797b42a4ef676`, os mesmos quatro inputs privados de `review_family.py`, a família ON inicial da parte 184, o seu recibo de revisão e o diretório que contém a revisão da parte 185. O programa exige um destino novo.
