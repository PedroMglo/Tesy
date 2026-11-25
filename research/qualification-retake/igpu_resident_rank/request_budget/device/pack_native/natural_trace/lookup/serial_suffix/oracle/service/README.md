# Quanto pode custar o serviço que um banco de 353 vítimas não elimina?

**Ao preço observado no P106, nenhuma escolha entre as 2 829 chaves oferecidas em T1 chega ao primeiro conteúdo final em 10 s nesta agenda.** Mesmo o melhor banco possível precisaria de recuperar pelo menos **2,511 s com AR** ou **583,807 ms com o prefixo B3 e o sufixo serial L25–35** noutro trabalho exposto. Estes limites já oferecem gratuitamente todos os hits, o prefixo B3, as cópias do banco e a recuperação de uma rejeição. A geometria, as reservas e a propagação até à drenagem das filas permanecem as observadas com AR. [Origem das escolhas de 353](../README.md) · [Contrato do preço](protocol.md)

| Agenda | Maior fração que a testemunha publicada admite nos quatro relógios | Primeira fração em que o certificado exclui qualquer banco de 353 |
|---|---:|---:|
| AR | 4,9568% | 10,6291% |
| Prefixo B3, sufixo serial | 47,4612% | 76,5753% |

A primeira coluna usa a lista oficial de cada agenda, escolhida retrospetivamente e mantida nos dois pedidos. O primeiro relógio que essa lista excede é o dos 10 s do P106 em ambos os casos. Os limiares da segunda coluna provêm de tetos matemáticos por relógio, avaliados numa grelha de milionésimos. Um eventual banco melhor permanece por demonstrar no intervalo entre as colunas. **A 0,5×, só o split deixa aberta a escolha de vítimas.** Nesse cenário a lista publicada excede a meta em 139,721 ms e qualquer lista tem no máximo 662,323 ms de margem P106 para todos os custos novos expostos antes da primeira peça. [Certificado individual](evidence/bank.json) · [Capacidade nos quatro relógios](evidence/dual.json) · [Aperto do primeiro final P106](evidence/mix.json)

### Margens dos dois pedidos

Cada célula dá **testemunha fixa / teto de qualquer banco** em segundos. Uma margem negativa indica quanto excede o orçamento. Uma margem superior positiva indica apenas espaço para investigar. O primeiro relógio mede até à chegada da primeira peça final ao cliente, a 10 s. O segundo usa os 47 tokens confirmados e a janela de decode nativa de 47/6 s. As 44 avaliações entre o prefill e a call 46 pertencem aos dois relógios. Os seus saldos têm utilização separada.

| Agenda e preço do serviço descoberto | P97 primeiro final | P97 decode | P106 primeiro final | P106 decode |
|---|---:|---:|---:|---:|
| AR · 0× | +1,475 / +1,639 | +2,956 / +3,398 | +0,315 / +0,410 | +2,738 / +3,108 |
| AR · 0,5× | −1,694 / −0,300 | +1,494 / +2,763 | −2,861 / −1,519 | +1,269 / +2,450 |
| AR · 1× | −4,863 / −1,233 | +0,032 / +2,676 | −6,036 / −2,511 | −0,199 / +2,363 |
| Split · 0× | +3,635 / +3,767 | +5,216 / +5,662 | +2,612 / +2,666 | +5,159 / +5,531 |
| Split · 0,5× | +0,900 / +2,105 | +4,198 / +5,275 | −0,140 / +0,662 | +4,127 / +5,117 |
| Split · 1× | −1,835 / +1,162 | +3,181 / +5,160 | −2,892 / −0,584 | +3,095 / +5,016 |

A testemunha AR oferece 314,812 ms antes da primeira peça do P106 quando o serviço descoberto é gratuito. Nas suas callbacks cobertas, **617 jobs de prefill** e **286 de decode até à peça** continuam a ser reservados e consumidos pela própria callback. Custaram 11,012 e 3,778 segundos-worker, respetivamente. Com quatro workers, a soma dos pisos de parede das waves é 3,414 e 2,937 s. Para o split restam 622 e 199 jobs, com 11,113 e 2,652 segundos-worker e pisos de parede de 3,440 e 2,064 s. Em ambos os casos o piso da cauda de decode nas callbacks cobertas é zero. O recibo conserva os preços próprios de P97 e P106 e o número de jobs nunca oferecidos. [Censos por fase](evidence/bank.json)

### Como se prova o teto

O custo de um job é o READ do pack mais os três SET sequenciais no mesmo worker, entre a reserva e a publicação, quando a própria callback exige a geração. Em cada wave afetada excluímos os hits e cobramos o maior entre a cadeia mais longa e um quarto da soma das cadeias, com a convenção de arredondamento inteira da análise anterior. Há um cálculo próprio dos preços no journal de cada pedido. No split, as 23 avaliações ordinárias usam todas as camadas e as 11 tentativas de bloco só continuam a pagar o sufixo serial das linhas conhecidas. Uma influência que nasça no prefixo gratuito pode alcançar uma callback ainda paga até à próxima drenagem.

Para o certificado exterior, cada wave tem um conjunto de chaves T1 que poderiam influenciá-la. Mesmo uma escolha com informação futura tem de suportar o custo dos jobs de chaves que nunca foram oferecidas nas callbacks em que reclama crédito. Os outros suportes dão um limite inferior para a cadeia ou para o quarto da soma quando falta uma chave elegível. O verificador agrupa os pesos de cobertura, concede uma parte de cada peso gratuitamente e atribui a outra às chaves que poderiam cobri-lo. As 353 maiores somas por chave limitam o ganho de qualquer banco. Qualquer combinação convexa dos quatro suportes de uma wave continua válida para **todos** os bancos. O primeiro limite P106 do split foi +37,870 ms a 1×. Repartir melhor cada peso de cobertura baixou esse limite a +31,701 ms. Permitir uma combinação própria de cada wave baixou-o a −583,807 ms. A reabertura calcula cada desigualdade com inteiros e verifica a prova publicada sem invocar o solver. [Primeira adenda](dual-protocol.md) · [Adenda por remap](per-wave-protocol.md)

**Condição de reabertura.** Para justificar um novo seletor causal com estes mecanismos no split, é necessário mostrar um preço efetivo inferior a 76,5753% neste regime, ou recuperar trabalho exposto que o envelope manteve. A 1× teriam de desaparecer pelo menos 583 806 805 ns adicionais até à peça P106, além de pagar a construção do banco, o prefixo do verificador, o transporte e o rollback. A 0,5× persiste uma pergunta verificável sobre a seleção e esses custos. A capacidade superior de 662,323 ms é um teto para o total mesmo que a candidata tenha 23 avaliações AR e 11 verificações híbridas numericamente exatas. A captura B3 correspondente, a velocidade do serviço depois de alterar a agenda e o efeito real dos hits após uma drenagem continuam desconhecidos.

### Reprodução

Pré-registos e código por etapa: preço em `ad18fb13` e `9cecf432`, dual por relógio em `0fd3cb48` e `14c4cad3`, mistura por remap em `82d6e772` e `0c169cd1`. Em duas execuções de cada etapa, o preço demorou 7,17/7,27 s (77 488/77 628 KiB RSS), o dual 2,88/2,86 s (72 276/71 508 KiB) e o aperto final 1,38/1,41 s (72 604/72 516 KiB). Os dois replays adicionais dos certificados publicados, com criação de subprocessos bloqueada, demoraram 1,30/1,28 s e reproduziram os recibos. Sete testes sintéticos, incluindo enumeração exaustiva e contraprovas de pesos inválidos, passaram. Zero forwards e zero leitura de pesos.

A partir desta pasta, `PARTS` identifica o arquivo das partes 97/106, `INTERSECTION` o recibo antecedente de SHA 667700ad…c955e, `ORACLE` a pasta com as duas listas e o recibo de capacidade, e `FRESH` um diretório privado existente. Usar destinos subordinados novos.

```sh
prlimit --as=536870912 --cpu=90 -- python3 -IB score.py \
  --archive "$PARTS" --intersection "$INTERSECTION" --capacity-dir "$ORACLE" \
  --new-output-dir "$FRESH/price"
cmp "$FRESH/price/receipt.json" evidence/bank.json
python3 -IB dual.py --archive "$PARTS" --previous evidence/bank.json \
  --witnesses "$ORACLE/witnesses.json" --shares evidence/dual-shares.json.gz \
  --shares-sha256 f364e097c005ee151803ee0f441dff22680964a298237ec895fec980918a5ae6 \
  --new-output-dir "$FRESH/dual"
cmp "$FRESH/dual/receipt.json" evidence/dual.json
python3 -IB mix.py --archive "$PARTS" --previous evidence/bank.json \
  --previous-dual evidence/dual.json --witnesses "$ORACLE/witnesses.json" \
  --shares evidence/mix-shares.json.gz \
  --shares-sha256 54553ed850eae0f290cb9a9c9df9aaf456359739de91b52a8e5829a472ed05ba \
  --new-output-dir "$FRESH/mix"
cmp "$FRESH/mix/receipt.json" evidence/mix.json
```

Omitindo os dois argumentos de partilha, a mesma CLI gera novas sugestões no lp_solve local selado e reavalia todas as contas por inteiros. As provas comprimidas incluem apenas coeficientes e partilhas ordenadas. A sua interpretação exige as fontes e testemunhos privados autenticados.
