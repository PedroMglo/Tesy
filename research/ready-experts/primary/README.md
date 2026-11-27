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

Os tempos da tabela concedem acesso direto nos hits, toda a redução admissível nas 711 waves CPU elegíveis e zero aos READ e SET sem homólogo estrito. Conservam o cliente integral. No último braço há 37 READ de 13 221 888 B sem preço e 1 974 SET de geração (três componentes por reserva) sem a mesma slot e geração. Cobrar o preço por expert mesmo com destino físico diferente eleva o primeiro final para 11,105 / 11,960 s. Até oferecendo mais 646,428 ms no cliente de P106, o melhor piso com o emparelhamento estrito permanece em 10,630 s. Nenhum preço não negativo dos READ desconhecidos salva esses braços sob as hipóteses congeladas. A comparação entre dois limites com quantidades diferentes de serviço oferecido gratuitamente não mede uma aceleração.

Os três journals concordam nas decisões lógicas originais, em 2 987 callbacks, 2 354 reservas, slots, gerações e na seleção inicial. Cada política usa o próprio estado desde o prefill até ao fim do decode. A prioridade induz 2 480 reservas. Se fosse necessário restituir o primário original no primeiro decode, haveria 19 membros a repor, 306 movimentos CPU e 122 CUDA, com 4 045 075 200 e 1 612 742 400 B de payload. O recibo identifica alterações de idades, gerações e relógios das camadas e os custos por banco.

**FORMAL para a população de primeiras aquisições.** Das rotas do próprio target surgem 954 chaves que faltavam simultaneamente aos 1 440 slots de entrada e às 353 marcas seladas em T1. Nos dois primários, a primeira reserva de cada uma serve exatamente a primeira região que a exige. São 726 no prefill, 224 no decode antes do primeiro final e quatro na cauda. Qualquer política que só possa adquirir à procura, com o mesmo conteúdo inicial, tem de obter essas chaves. **Condicional aos preços originais**, mesmo concedendo capacidade ilimitada daí em diante, o primeiro final com grafo e cliente integrais e os SET obrigatórios é 8,940 / 10,031 s. Com todos esses SET gratuitos desce para 8,564 / 9,628 s. O limite físico depende do preço, da entrada e de quando o produtor recebe a identidade.

As duas reproduções em árvore limpa no commit `419a1fb3` (árvore `7759606b`) consumiram 6,11 e 6,12 s e até 169 816 KiB de RSS. SHA-256 dos dois recibos `f1ae0a26073dbf74eba9e10a204d28b2a41abfd42ddeeac367881bf6f63a70c1`. Sem novos forwards nem uso de GPU. O melhor resultado natural anteriormente medido com pack e trace desligado permanece 18,313 s até ao primeiro conteúdo final e 5,361 tok/s. M3 PARTIAL e M4 NOT_MET. [Controlo natural](../../qualification-retake/packed_nvme_manifest/server_profile/conversation/ordens.md)

```sh
out=$(mktemp -d)
python3 -IB research/ready-experts/primary/replay.py --archive "$TESY_ARCHIVE" \
  --placement "$TESY_RENEWAL_ARCHIVE/placement" --new-output-dir "$out/primary"
cmp "$out/primary/receipt.json" research/ready-experts/primary/evidence/receipt.json
```
