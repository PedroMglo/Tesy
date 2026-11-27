# O que se ganha ao mudar a vítima do primário no segundo turno

**NO_GO para justificar um backend novo com estas seis combinações.** Dar prioridade à expulsão de um expert recuperável poupa 172 leituras no banco fixo. Com o banco que decide por frequência, a mesma mudança poupa uma leitura no pedido inteiro. Mesmo oferecendo todas as cópias sem preço, a melhor combinação ainda excede o prazo de primeiro conteúdo nos dois processos do portátil. O resultado é **TRACE_DERIVED** sobre uma conversa nominal, repetida em dois processos. [Protocolo prospetivo](protocol.md) · [Recibo completo](evidence/receipt.json)

| Primário durante T2 | Banco de 353 | Leituras prefill / decode | Primeiro final P97 / P106 (s) | Decode P97 / P106 (s para 47 IDs) |
|---|---|---:|---:|---:|
| R0 | Fixo | 1 108 / 919 | 12,503 / 13,320 | 6,892 / 7,019 |
| R0 | Recência | 974 / 776 | 11,621 / 12,454 | 6,276 / 6,433 |
| R0 | Frequência | 880 / 783 | 11,245 / 12,088 | 6,362 / 6,512 |
| Vítima recuperável primeiro | Fixo | 1 058 / 797 | 11,217 / 12,005 | 5,926 / 6,027 |
| Vítima recuperável primeiro | Recência | 975 / 822 | 10,886 / 11,657 | 5,753 / 5,847 |
| Vítima recuperável primeiro | Frequência | 877 / 785 | **10,465 / 11,276** | **5,739 / 5,843** |

Os tempos da tabela concedem acesso direto nos hits, toda a redução admissível nas 711 waves CPU elegíveis e zero aos READ e SET sem homólogo estrito. Conservam o cliente integral. No último braço há 37 READ de 13 221 888 B sem preço. Em 1 974 reservas falta o preço da soma dos três SET para a mesma slot e geração. Cobrar o preço por expert mesmo com destino físico diferente eleva o primeiro final para 11,105 / 11,960 s. Até oferecendo mais 646,428 ms no cliente de P106, o melhor piso com o emparelhamento estrito permanece em 10,630 s. Nenhum preço não negativo dos READ desconhecidos salva esses braços sob as hipóteses congeladas. A comparação entre dois limites com quantidades diferentes de serviço oferecido gratuitamente não mede uma aceleração.

Os três journals concordam nas decisões lógicas originais, em 2 987 callbacks, 2 354 reservas, slots, gerações e na seleção inicial. Cada política usa o próprio estado desde o prefill até ao fim do decode. A prioridade induz 2 480 reservas. Se fosse necessário restituir o primário original no primeiro decode, haveria 19 membros a repor, 306 movimentos CPU e 122 CUDA, com 4 045 075 200 e 1 612 742 400 B de payload. O recibo identifica alterações de idades, gerações e relógios das camadas e os custos por banco.

**FORMAL para a população de primeiras aquisições.** Das rotas do próprio target surgem 954 chaves que faltavam simultaneamente aos 1 440 slots de entrada e às 353 marcas seladas em T1. Nos dois primários, a primeira reserva de cada uma serve exatamente a primeira região que a exige. São 726 no prefill, 224 no decode antes do primeiro final e quatro na cauda. Qualquer política que só possa adquirir à procura, com o mesmo conteúdo inicial, tem de obter essas chaves. **Condicional aos preços originais**, mesmo concedendo capacidade ilimitada daí em diante, o primeiro final com grafo e cliente integrais e os SET obrigatórios é 8,940 / 10,031 s. Com todos esses SET gratuitos desce para 8,564 / 9,628 s. O limite físico depende do preço, da entrada e de quando o produtor recebe a identidade.

As duas reproduções em árvore limpa no commit `419a1fb3` (árvore `7759606b`) consumiram 6,11 e 6,12 s e até 169 816 KiB de RSS. SHA-256 dos dois recibos `f1ae0a26073dbf74eba9e10a204d28b2a41abfd42ddeeac367881bf6f63a70c1`. Sem novos forwards nem uso de GPU. O melhor resultado natural anteriormente medido com pack e trace desligado permanece 18,313 s até ao primeiro conteúdo final e 5,361 tok/s. M3 PARTIAL e M4 NOT_MET. [Controlo natural](../../qualification-retake/packed_nvme_manifest/server_profile/conversation/ordens.md)

```sh
out=$(mktemp -d)
python3 -IB research/ready-experts/primary/replay.py --archive "$TESY_ARCHIVE" \
  --placement "$TESY_RENEWAL_ARCHIVE/placement" --new-output-dir "$out/primary"
cmp "$out/primary/receipt.json" research/ready-experts/primary/evidence/receipt.json
```

## Mudar os residentes desde a primeira pergunta

**NO_GO para basear um backend novo na recorrência por visita da camada.** Manter a penúltima utilização de cada expert desde T1 mudou 167 dos 1 440 residentes primários à entrada de T2 e 234 das 353 chaves do banco de vítimas. As primeiras aquisições obrigatórias do prefill desceram de 726 para 706. Face ao gestor nativo com o mesmo tipo de banco, a agenda inteira subiu de 1 662 para 1 911 leituras em T2. O cálculo da política acede só ao passado do target. [Pré-registo e antecedente LRU-K](turns.md) · [Quatro trajetórias e todos os relógios](evidence/two-turns.json)

| Escolha em T1 / T2 | Leituras T1 prefill / decode | Capturas para o banco em T1 | Leituras T2 prefill / decode | Primeiro final P97 / P106 (s) | Decode P97 / P106 (s, 47 IDs) |
|---|---:|---:|---:|---:|---:|
| Nativo / calor com prioridade | 3 418 / 2 309 | 4 506 | 877 / 785 | 10,465 / 11,276 | 5,739 / 5,843 |
| Nativo / K=2 | 3 418 / 2 309 | 4 506 | 864 / 1 054 | 10,152 / 10,931 | 5,645 / 5,738 |
| K=1 / K=1 | 3 274 / 2 430 | 4 502 | 931 / 993 | 10,165 / 10,957 | 5,640 / 5,741 |
| K=2 / K=2 | 3 302 / 2 502 | 4 567 | 911 / 1 000 | 10,184 / 10,963 | 5,621 / 5,704 |

São pisos condicionais de serviço com o mesmo tratamento favorável da tabela anterior. As três políticas alternativas receberam respetivamente 353, 354 e 318 READ sem preço e 2 736, 2 774 e 2 822 entregas por geração sem preço estrito. O primeiro final falha já no P97. Nenhuma das três passa mesmo oferecendo todo o crédito extra de cliente em P106. Dar um preço nulo diferente a cada população impede usar as diferenças entre estes segundos como ganhos medidos. Os 5 727 READ reais do T1 nativo e as idades do snapshot em P63 ancoram o controlo. Os READ dos outros T1 e todas as capturas do banco são contagens de agenda. O preço dos novos READ e das cópias de T1 é desconhecido. Não houve novas inferências nem observação de KV, logits ou consumo de GPU. As condições para reabrir incluem uma redução demonstrada do serviço das faltas ou uma disponibilidade anterior dos bytes no percurso do pedido.

O código correu na árvore limpa `ba7b2e07`. Os dois processos de seleção leram apenas o prefixo autenticado, com 74 278 quartetos, e levaram 4,66 / 4,65 s. Os dois selos coincidiram, SHA-256 `f2d831599f5f4fd2caf188d1ecf31b034995979b567e488f1e1d798feb3fe896`. Os avaliadores reconstruíram o selo antes de ler T2. A primeira avaliação levou 8,22 s e o pico máximo nas duas foi 173 236 KiB de RSS. O recibo tem SHA-256 `c8c83442b10e5da2e8d1c5d57e3023c8abcf84d076b92829ebbc7916f8815ea7`.

```sh
u=research/ready-experts/primary
out=$(mktemp -d)
arm="$TESY_ARCHIVE/part-106/tesy-full-prefix-natural-physical-20261125-r01/ON"
python3 -IB "$u/two_turns.py" train --t1-arm "$arm" --new-output-dir "$out/plan"
python3 -IB "$u/two_turns.py" score --archive "$TESY_ARCHIVE" \
  --placement "$TESY_RENEWAL_ARCHIVE/placement" --plan "$out/plan/plan.json" \
  --plan-sha256 f2d831599f5f4fd2caf188d1ecf31b034995979b567e488f1e1d798feb3fe896 \
  --new-output-dir "$out/score"
cmp "$out/score/receipt.json" "$u/evidence/two-turns.json"
```
