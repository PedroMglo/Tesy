# Duas tiles podem renovar a reserva em RAM sem disputar a mesma vítima?

**NO_GO para um backend dedicado também com o banco renovável por estágio, a preços de serviço fixos.** O banco aumentou de 155 para **371** os acertos no prefill do segundo turno, com a mesma capacidade de 353 experts. O piso de primeiro conteúdo final desceu de 12,213 para **10,669 s** em P97 e de 13,165 para **11,622 s** em P106. Ambos os pares comparam o layout treinado, duas tiles em pipeline e cópias dos hits gratuitas. O decode tem margem na projeção. A velocidade desta combinação numa conversa continua por medir. O melhor turno nominal físico segue em **17,689 s / 5,357 tok/s**, com pack e fusão CPU no executor atual. R0 slots40-persistent, M3 PARTIAL e M4 NOT_MET. [Protocolo anterior à avaliação](tier-bank.md) · [Resultados por braço](evidence-tier-20261128-r01/receipt.json) · [Reserva fixa e ensaio no NVMe](README.md)

## Uma ordem que muda o resultado e outra que o conserva

O primeiro turno tinha 4 091 reservas nas camadas 0–24 e 1 636 nas camadas 25–35. Esta única observação definiu os dois grupos de **252 e 101 slots secundários**, ambos na RAM. As 353 vítimas originais continham 48 duplicados do primário. À entrada de T2 havia 227 e 78 cópias exclusivas. Atingiram o máximo de 252 e 101. Cada transação identifica a chave `(camada, slot primário, geração, expert)`, a vítima anterior e os slots secundários de promoção e captura. O controlador utiliza a frequência vista até à reserva presente e desempata por antiguidade.

| Portador da reserva | Acertos no prefill | Decode até à primeira peça | Cauda de decode | Total de acertos |
|---|---:|---:|---:|---:|
| Banco global, ordem da captura | 383 | 304 | 4 | 691 |
| Banco global, adiantar a frente da próxima tile | 367 | 303 | 4 | 674 |
| Dois bancos, em ambas as ordens | **371** | **299** | **4** | **674** |

No banco global, mudar a ordem alterou a fonte de 17 gerações. Duas ordens só demonstram a ambiguidade dessa política. Nos dois bancos, cada reserva modifica o contador, a propriedade e a lista livre exclusivamente do seu estágio. A sequência dentro de cada estágio mantém-se, pelo que qualquer intercalação que preserve essas sequências produz por indução as mesmas fontes e os mesmos slots físicos locais. As duas execuções verificaram essa igualdade em todas as 2 354 transações e no estado final. O argumento fixa a escolha das vítimas primárias de R0 por camada. Uma execução que dependa de uma época global do primário tem de comprovar essa premissa.

## Preço no pedido inteiro

| Banco renovável e pipeline | Primeiro final P97 / P106 | Decode de 47 IDs P97 / P106 |
|---|---:|---:|
| Disposição numérica, SET pago | 11,075 / 11,992 s | 7,209 / 7,442 s |
| Disposição treinada, SET pago | **10,843 / 11,806 s** | **6,934 / 7,187 s** |
| Disposição numérica, SET dos hits gratuito | 10,899 / 11,807 s | 7,084 / 7,307 s |
| Disposição treinada, SET dos hits gratuito | **10,669 / 11,622 s** | **6,809 / 7,052 s** |

Estas durações são pisos **TRACE_DERIVED_CONDITIONAL**. A projeção concede latência zero às leituras de vizinhos físicos, conserva os bytes deles no link e cobra o serviço isolado das restantes gerações. Os dois travões independentes de banda, 4,5 e 8 GB/s, deram aqui os mesmos pisos. O trabalho por camada e os custos exteriores já impõem o maior termo. Com 371 acertos evitam-se 4 904 323 200 B de payload NVMe no prefill. Restam 892 aquisições e 11 791 526 400 B. As 175 adjacências de prefill caem para 97 depois de servir os hits pela RAM. As 52 de decode caem para 27. A reserva também exige capturar 14 831 942 400 B só no prefill, incluindo 5 406 652 800 B de vítimas do estágio com experts CUDA. A agenda concede tempo zero a essas capturas. O total T2 de captura soma 26 055 043 200 B de payload lógico. Nenhum destes números mede tráfego físico DRAM ou PCIe.

O banco ultrapassa as 191 admissões da condição de banda anterior. O primeiro conteúdo final ainda exige recuperar **0,669 s e 1,622 s** no relógio integral dos dois pedidos, mesmo oferecendo a cópia dos hits gratuitamente. Conceder também os 646,428 ms pré-stream de P106 ainda deixa um piso de **10,976 s**. Por isso a retenção renovável é um mecanismo complementar com melhor cobertura. Uma proposta de substituir o backend terá de alterar a data de disponibilidade dos experts frios isolados, o custo do cálculo serial ou o número de avanços confirmados pelo target, e pagar as capturas, a coordenação e a proteção do segundo caso. A sessão sustentada do novo candidato e o seu consumo máximo no portátil ficam NOT_RUN.

A execução nos dois journals demorou 1,75 s, com até 74 616 KiB de RSS. O replay da prova pública usou 0,46 s e 35 128 KiB. Os recibos e as tabelas de transações comprimidas saíram idênticos byte a byte. A seleção e a agenda são calculadas sem pesos e sem GPU. A investigação anterior mediu a wave e os seus sete pesos no NVMe interno. [Commit, árvore e comandos](evidence-tier-20261128-r01/provenance.json) · [Manifesto de arquivo privado](evidence-tier-20261128-r01/archive.json)

~~~sh
s=research/ready-experts/layer/prefix/wave
python3 -IB "$s/tier_bank.py" --witness "$s/evidence-tier-20261128-r01/transactions.json.gz" \
  --new-output-dir "$NOVA_RAIZ"
cmp "$NOVA_RAIZ/receipt.json" "$s/evidence-tier-20261128-r01/receipt.json"
~~~
