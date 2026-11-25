# Quantas chaves teria o T1 de deixar na cache secundária?

**192 chaves são o mínimo para fazer o piso temporal tocar os 10 s com as durações R0.** Com as 191 melhores, o piso do primeiro conteúdo final ainda é 10,002106 s. Com 192 cai para 9,994385 s, dando só 5,615 ms de margem ao modelo otimista. A escala de serviço 0,8 precisa de 84 chaves. No denominador contratual M4, o piso de volume do prefill impõe em ambos os casos pelo menos **224 chaves úteis**. A capacidade L2 de 239 comporta cada mínimo individual. Uma seleção comum aos dois objetivos e a sua realização sem acesso ao futuro permanecem **INCONCLUSIVE**. [Recibo reproduzido](receipt.json) · [Pré-registo](protocol.md)

## Tempo até ao primeiro conteúdo final

**TRACE_DERIVED.** A entrada é a trajetória validada do segundo pedido. O serviço contém 875 primeiras reservas frias de identidades distintas, com as três leituras seriais pelo mesmo worker, em 441 waves contidas na janela. Mantêm-se o instante de libertação da wave e 5,996896 s no exterior das callbacks. Concedem-se uma L2 preparada antes de T2, entrega gratuita ao primário, quatro workers e todos os custos omitidos pelo piso original. As durações efetivas dos preads observados incluem a contenção em R0. O cenário 0,8 multiplica o piso de serviço pela fração 4/5. [Conservação e exclusões](../mandatory.md) · [Plano autenticado de leituras](../cold_read_fixture/protocol.md)

| Escala dos READ | Piso com K=0 | Mínimo temporal e payload preparado | Piso K−1 → K | Piso com K=239 | Piso com K=353 |
|---|---:|---:|---:|---:|---:|
| 1 | 12,228464 s | 192 / 2 538 086 400 B | 10,002106 → 9,994385 s | 9,646843 s | 8,863601 s |
| 4/5 | 10,982150 s | 84 / 1 110 412 800 B | 10,006463 → 9,997498 s | 8,916854 s | 8,290260 s |

Para q chaves aquecidas numa wave, remover as q cadeias mais longas minimiza ao mesmo tempo a parte serial máxima e a soma das restantes. A troca de uma cadeia removida por outra maior nunca aumenta esses dois limites. O programa soma os pisos por programação dinâmica, cobrando exatamente k chaves no total. Cada chave temporal aparece numa única wave. Cada custo apresentado tem uma seleção de k chaves reconstruída e verificada pelo recálculo do piso. As seleções ideais e os seus hashes dependem do sufixo já observado; a repetição resolve os empates por ordem fixa. A enumeração exaustiva dos testes inclui waves com mais de quatro cadeias, empates e ganhos que requerem várias chaves. [Solver](screen.py) · [Testes](test_screen.py)

## Volume das duas chamadas de prefill

O primeiro serviço de cada uma das 1051 identidades obrigatórias custa 13 219 200 B de payload; cada entrada útil aquecida pode retirar um payload desse piso. Com 239 entradas escolhidas para volume restam 10 733 990 400 B, com 353 restam 9 227 001 600 B. A L2 mais pequena reserva 3 212 959 744 B físicos no orçamento de RAM do crivo; a maior reserva 4 720 263 168 B, incluindo montagem, alinhamento e metadados. Os números de bytes desta tabela são lógicos; o requisito mínimo em T1 quantifica o que tem de estar materializado antes de T2. Uma leitura que o próprio T1 já exigia poderá fornecer essa cópia. [Crivo de volume e memória](../host_cache/README.md)

| Orçamento a 4,5 GB/s | Mínimo por volume | Payload mínimo já preparado | Margem de volume K=239 / K=353 | Mínimo necessário para volume e tempo 1 / 4/5 |
|---|---:|---:|---:|---:|
| 47 saídas M4 · 10 938 366 806 B | 224 | 2 961 100 800 B | 204 376 406 / 1 711 365 206 B | 224 / 224 |
| 46 avaliações · 11 688 366 807 B | 167 | 2 207 606 400 B | 954 376 407 / 2 461 365 207 B | 192 / 167 |

A última coluna é o máximo dos dois mínimos independentes. O conjunto temporal pode conter chaves úteis apenas durante o decode. Por isso, 15 lugares acima do mínimo de volume contratual, na cache de 239, não representam 15 escolhas livres numa agenda que cumpra simultaneamente os dois limites. A pergunta seguinte, ainda respondível no journal existente, é se há uma mesma seleção inicial que passe ambos os pisos. Havendo essa margem, uma captura de T1 só tem interesse se revelar quais dessas identidades uma política causal consegue materializar, a que custo, por quanto tempo e com que efeito no primeiro turno, na memória e no primeiro decode. Alcançar um piso otimista ainda exige demonstrar uma agenda executável e validar o outro caso. M4 permanece NOT_MET.

## Reprodução

Pré-registo em `480ee50b`; código e testes em `70446169`. Autenticar as duas cópias do plano e o journal ON original. Os dois processos Python terminaram em 0,18 s cada, com 47 280 e 46 560 KiB de RSS máximo. Os recibos são idênticos byte a byte, SHA-256 `87b2c4bcf96695a04e6f70adff14adf7d5ed24e7ef77e81218dafc3b3da14441`. Não houve GPU, abertura de pesos nem novas conversas.

```sh
timeout 120s prlimit --as=536870912 --cpu=120 --fsize=1048576 -- \
  python3 -IB research/qualification-retake/phase_fd/integrated/warm_oracle/screen.py \
    --plan-dir "$PLAN" --plan-sha256 c5b9cac1354ff9d58563d1a8167a39abeb74ac376d5741cedb8de203d62f862b \
    --journal "$ON/raw/events.pfj" --new-output-dir "$NEW"
cmp "$NEW/receipt.json" research/qualification-retake/phase_fd/integrated/warm_oracle/receipt.json
```
