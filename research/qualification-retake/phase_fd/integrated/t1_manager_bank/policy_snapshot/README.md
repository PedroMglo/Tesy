# O estado de escolha da vítima à entrada de T2

**PASS da captura em CPU. O efeito da prioridade no pedido da parte 40 continua INCONCLUSIVE.** O C269 real escolheu a mesma vítima de R0 em quatro estados com os mesmos dados visíveis em PFJ1. Ao dar prioridade aos dois residentes recuperáveis do banco, o resultado mudou tanto com a frequência como com a ordem de recência. Uma aquisição do estado no T2 de um próximo par OFF/ON pode testar a política antes de integrar o banco no endpoint. [Protocolo](protocol.md) · [Recibo dos oito braços](receipt.json)

| Braço | Estado da observação | Bytes adicionais | Vítima R0 | Vítima com prioridade |
|---|---|---:|---:|---:|
| OFF | Só PFJ1 | 0 | 0 | 1 |
| Frequência A / B | Completa, difere um contador | 48 800 cada | 0 / 0 | 1 / 2 |
| Idade A / B | Completa, trocam-se dois carimbos | 48 800 cada | 0 / 0 | 1 / 2 |
| Pendente | 2 entradas FIFO da mesma geração, 1 claim e 2 slots LOADING | 128 | 0 | 0 |
| Sem a chamada | Ausente | 128 | 0 | 1 |
| Chamada repetida | Ambígua | 128 | 0 | 1 |

Cada corte completo contém 6 084 palavras de política. A revisão independente também verificou 1 440 vínculos e gerações, 108 componentes de peso, a fila ordenada e a conclusão de cada processo. Os controlos negativos não publicaram uma tabela elegível. As quatro threads de I/O estavam configuradas, com zero workers lançados. Os descritores do caso pendente foram injetados e mantidos até RETURN. A fixture chamou diretamente o seletor nativo sob o mutex, sem esperar por I/O. O braço OFF mantém o PFJ1 em funcionamento e desativa apenas o ficheiro adicional.

### A ambiguidade é alcançável no seletor?

**MEDIDO** nos oito braços acima com estados sintéticos injetados. Por exemplo, o seed atribui frequência a experts ausentes com gerações iniciais iguais a um. Estes valores testam a captura integral e a escolha local. A trajetória que os gerou não foi reproduzida.

**FORMAL**, com um exemplo independente de uma camada e rotas admissíveis. Começar vazio com 40 slots e servir dez remaps simples com quatro experts distintos em cada linha, de [0,1,2,3] a [36,37,38,39]. O contador global começa a zero. Mesmo servindo as 36 camadas em cada uma das doze chamadas do exemplo mais longo, há 432 remaps, abaixo do intervalo de decaimento de 2 304. Após as dez chamadas iniciais cada residente tem frequência 1, geração 1 e slot igual ao ID. O slot 0 é o mais antigo. Fixar o banco em {1,2} e efetuar as seguintes operações, todas hits, antes da nova falta. Os ranks e respetiva ordem são parte das premissas.

- Servir [1,2,3,4] numa história e [2,1,3,4] na outra. Os dois experts recuperáveis terminam com frequência 2. A ordem de idade troca e o banco escolhe respetivamente o slot 1 ou o 2.
- Servir [1,3,4,5] numa história e [2,3,4,5] na outra, seguidas pela mesma linha [1,2,3,4]. O último uso de cada slot é idêntico nas duas histórias. As frequências dos experts 1 e 2 terminam em (3,2) e (2,3), logo a prioridade escolhe o slot 2 ou o 1.

Em ambos os exemplos, os membros, as gerações, a fila vazia e a escolha original do slot 0 coincidem no corte. A diferença está no passado anterior ao corte. Isto prova que um snapshot só de residência não determina a política em geral. Para o pedido histórico, as observações adicionais da parte 40 podem restringir as histórias compatíveis. Não foi demonstrada divergência do score desse pedido. [Campos observados no primeiro decode](../decode_entry/README.md)

### Aplicação ao próximo pedido

O sidecar opt-in foi exercitado na cópia privada da instrumentação PFJ1 do C269, com o mesmo mutex de ENTER. Preserva `route_hotness` de todos os 128 experts por camada, `slot_last_use` de cada slot físico, `use_counter`, o contador global e o intervalo de decaimento. O remap simples incrementa uma vez por expert distinto e pode reduzir as frequências a metade em todas as camadas; o caminho multiwave incrementa o contador global sem esse incremento de hotness. A reserva e os ranks ativos atualizam a idade. Os ranks mascarados não a atualizam. A política de base exclui keep e LOADING, escolhe primeiro o vazio e depois desempata por frequência, idade e slot físico. [C152 e formato de referência](../../../../../../tools/c152_snapshot.inl) · [Semântica da política nos pins estudados](../../../../causal_prefix.md)

Para usar o ficheiro num pedido é preciso qualificar a extensão compilada no runtime, o vínculo ao PFJ1 e ao banco selado dessa execução, a paridade OFF/ON e o custo do observador. O replay deve reproduzir primeiro R0 contra as reservas e publicações observadas. Quando a nova política mudar a agenda, a ordem de publicação e a disponibilidade de candidatos têm de ser observadas no candidato ou limitadas em todas as ordens compatíveis. Continuam em aberto a reconstituição completa e os custos em T1 e T2.

**Proveniência e custo.** Protocolo congelado em `4e11587c`, implementação e medição em `47d81601`; uma compilação, oito processos CPU, sem forward, modelo ou GPU. A família demorou 1,575 s, incluindo 1,523 s até obter o executável e o inventário do loader. O pico do scope foi de 175 177 728 B com limite de 1 GiB e swap zero. O recibo bruto tem SHA-256 `e689fd19a7d78b5fb8833e63f761ebb2d46895953d970f534f1d4ea8dcb04264`. As revisões R01/R02 ficaram FAIL ao comparar tuplos do auditor com os arrays do JSON. R03/R04 repetiram a revisão sobre os mesmos bytes, normalizando a mesma representação JSON e reproduzindo `73b691d2ffcfb046dd2fe446387c2967c898c6ea1c10c7ce220b7320770e616b`. Os manifestos privados são `760e04c5986b12b43aa1d5f906a90cea9713b98c3a2ad74a80d642a0b61ee3f3` (parte 60, raw e FAILs) e `235ff9d7e85320ad13b89f707f913a7c6ff4f80d60417ea157ebb2b95ab1f736` (parte 61, revisões aprovadas).

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot
python3 -IB "$unit/test_review.py"
python3 -IB "$unit/compact.py" --family "$RAW" --new-output-dir "$NEW"
cmp "$unit/receipt.json" "$NEW/receipt.json"
```
